const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const pino = require('pino');
const express = require('express');
const cors = require('cors');
const QRCode = require('qrcode');
const fs = require('fs');
const path = require('path');

// ⚠️ MARCADOR DE BUILD — se esta linha NÃO aparecer no Registro de atividade ao
// iniciar, o app está rodando um motor ANTIGO (troque o motor/index.js certo e
// finalize processos node.exe órfãos antes de reiniciar).
const MOTOR_BUILD = '2026-07-20 · conexao-estavel-v4 (socket-unico, sem loop de QR)';

// ------------------------------------------------------------------
// SILENCIADOR DE RUÍDO DO libsignal
// A lib de criptografia (libsignal) imprime, direto no console, erros de
// decodificação de mensagens RECEBIDAS que são INOFENSIVOS para o robô:
// "Bad MAC", "Key used already or never filled", "Failed to decrypt
// message", "Session error". Acontecem com mensagens antigas/duplicadas ou
// de membros de grupo cujo handshake ainda não foi feito — e NÃO afetam o
// envio dos relatórios. Sem este filtro, eles INUNDAM o log do app.
// Aqui filtramos apenas esse ruído específico; todo o resto do log continua.
// ------------------------------------------------------------------
const _padroesRuidoLibsignal = [
    'Bad MAC',
    'Failed to decrypt message',
    'Session error',
    'MessageCounterError',
    'Key used already or never filled',
    // Ruído de rotação de sessão do libsignal (despeja objetos enormes com
    // <Buffer ...> no log). Tudo inofensivo — só sujava a tela.
    'Closing session',
    'Closing open session',
    'incoming prekey bundle',
    'Decrypted message with closed session',
    'SessionEntry',
];
let _ruidoSuprimido = 0;
function _ehRuidoLibsignal(args) {
    const texto = args.map(a => (a && a.stack) ? a.stack : String(a)).join(' ');
    return _padroesRuidoLibsignal.some(p => texto.includes(p));
}
const _logOriginal = console.log.bind(console);
const _errOriginal = console.error.bind(console);
function _filtrar(orig, args) {
    if (_ehRuidoLibsignal(args)) {
        _ruidoSuprimido++;
        // De tempos em tempos avisa que está ignorando (para não parecer travado).
        if (_ruidoSuprimido % 200 === 0) {
            _logOriginal(`ℹ️ ${_ruidoSuprimido} mensagens de grupo não decifráveis ignoradas (normal, não afeta os relatórios).`);
        }
        return;
    }
    orig(...args);
}
console.log = (...args) => _filtrar(_logOriginal, args);
console.error = (...args) => _filtrar(_errOriginal, args);

const app = express();
app.use(cors());
app.use(express.json({ limit: '50mb' }));

let sock;
let ultimoQrBase64 = null;              // "data:image/png;base64,...." pronto para <img src="...">
let statusConexao = 'AGUARDANDO_QR';    // AGUARDANDO_QR | CONECTADO | DESCONECTADO

// --------------------------------------------------------------------
// CONTROLE DE RECONEXÃO — impede múltiplos sockets/QRs simultâneos.
// Sem isto, cada evento de 'close' (e o /reparear) agendava sua própria
// reconexão; elas se empilhavam e criavam VÁRIOS sockets ao mesmo tempo ->
// "novo QR a cada 30s" e o erro "Cannot read ... 'id'" ao enviar durante a
// troca de socket. Agora: no máximo UMA conexão em andamento e UM timer de
// reconexão por vez.
// --------------------------------------------------------------------
let conectando = false;        // true enquanto um socket está sendo criado
let timerReconexao = null;     // timer único de reconexão pendente

function agendarReconexao(delayMs, motivo) {
    if (timerReconexao) return;          // já há uma reconexão agendada: não empilha
    console.log(`🕒 Reconexão agendada em ${Math.round(delayMs / 1000)}s (${motivo}).`);
    timerReconexao = setTimeout(() => {
        timerReconexao = null;
        connectToWhatsApp();
    }, delayMs);
}

// Fila de comandos vindos do WhatsApp (ex: ACATAR) que o app (main_app.py)
// consome via GET /comandos. É esvaziada a cada leitura.
let filaComandos = [];

const caminhoInscritos = path.join(__dirname, 'subscribers.json');
const caminhoConfigJidAntigo = path.join(__dirname, 'registered_jid.json'); // legado (1 contato)

// --------------------------------------------------------------------
// INSCRITOS (múltiplos contatos/grupos) — START adiciona, STOP remove.
// Substitui o modelo antigo de 1 único JID: agora qualquer contato ou
// grupo que enviar START passa a receber os relatórios, e quem enviar
// STOP para de receber — sem precisar deslogar/relogar o WhatsApp.
// --------------------------------------------------------------------
function lerInscritos() {
    try {
        const dados = JSON.parse(fs.readFileSync(caminhoInscritos, 'utf8'));
        if (Array.isArray(dados.subscribers)) return dados.subscribers;
    } catch (e) { /* arquivo ainda não existe */ }

    // ⚠️ NÃO migramos mais o registered_jid.json automaticamente. Aquela migração
    // silenciosa adicionava um contato antigo sem o usuário perceber — e os
    // relatórios acabavam indo para um chat que ele NUNCA escolheu (bug grave).
    // Agora a lista começa VAZIA e só cresce por START explícito (ou pelo painel
    // do app). Nunca há inscrição silenciosa.
    return [];
}

function salvarInscritos(lista) {
    // Remove duplicados preservando a ordem.
    const unicos = [...new Set(lista)];
    fs.writeFileSync(caminhoInscritos, JSON.stringify({ subscribers: unicos }, null, 2));
}

function adicionarInscrito(jid) {
    const lista = lerInscritos();
    if (lista.includes(jid)) return false;   // já estava inscrito
    lista.push(jid);
    salvarInscritos(lista);
    return true;
}

function removerInscrito(jid) {
    const lista = lerInscritos();
    if (!lista.includes(jid)) return false;  // não estava inscrito
    salvarInscritos(lista.filter(j => j !== jid));
    return true;
}

async function connectToWhatsApp() {
    // Trava anti-concorrência: nunca cria dois sockets ao mesmo tempo.
    if (conectando) {
        console.log('⏭️ Conexão já em andamento — ignorando chamada duplicada.');
        return;
    }
    conectando = true;

    // Derruba o socket anterior E seus listeners antes de criar um novo. Remover
    // os listeners ANTES de encerrar evita que o 'close' do socket velho dispare
    // outra reconexão (era a origem da tempestade de QRs).
    if (sock) {
        try { sock.ev.removeAllListeners(); } catch (e) {}
        try { sock.end(undefined); } catch (e) {}
        sock = null;
    }

    try {
        const { state, saveCreds } = await useMultiFileAuthState(path.join(__dirname, 'auth_smc'));

        // Busca a versão ATUAL do protocolo do WhatsApp Web. Sem isso, o Baileys
        // usa uma versão padrão embutida na lib que pode estar desatualizada,
        // causando rejeição da conexão (código 405) e o QR nunca é gerado.
        const { version, isLatest } = await fetchLatestBaileysVersion();
        console.log(`Usando versão do protocolo WhatsApp Web: ${version.join('.')} (mais recente: ${isLatest})`);

        sock = makeWASocket({
        version,
        auth: state,
        logger: pino({ level: 'silent' }),
        browser: ['SMC Quant Pro', 'Chrome', '1.0.0'],
        // Não se marca "online": bots que ficam online às vezes deixam de
        // RECEBER mensagens (o WhatsApp para de entregar as notificações ao
        // aparelho linkado). Ficar "offline" mantém a entrada de mensagens.
        markOnlineOnConnect: false,
        syncFullHistory: false,
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            try {
                ultimoQrBase64 = await QRCode.toDataURL(qr);
                statusConexao = 'AGUARDANDO_QR';
                console.log('📷 Novo QR gerado — disponível em GET /qrcode');
            } catch (err) {
                console.log(`❌ Erro ao gerar imagem do QR: ${err}`);
            }
        }

        if (connection === 'open') {
            statusConexao = 'CONECTADO';
            ultimoQrBase64 = null;
            console.log('✅ CONECTADO: WhatsApp pareado com sucesso!');
            console.log(`   (isNewLogin=${update.isNewLogin}, `
                + `receivedPendingNotifications=${update.receivedPendingNotifications})`);
            console.log('   Se você mandar mensagem e NÃO aparecer "📥 upsert recebido", '
                + 'a sessão parou de receber — force o re-pareamento em '
                + 'http://localhost:3939/reparear');
        }

        if (connection === 'close') {
            statusConexao = 'DESCONECTADO';
            const codigoErro = lastDisconnect?.error?.output?.statusCode;
            const foiLogout = codigoErro === DisconnectReason.loggedOut;
            console.log(`⚠️ Conexão fechada (código ${codigoErro}). Logout: ${foiLogout}`);

            if (foiLogout) {
                // Sessão foi invalidada pelo WhatsApp (ex: removida nos
                // "Dispositivos conectados" do celular). Reconectar com as
                // mesmas credenciais nunca vai funcionar — é preciso parear
                // do zero. Em vez de exigir que o cliente apague pastas na
                // mão, o motor faz isso sozinho e já gera um QR novo.
                console.log('🔄 Sessão inválida — limpando credenciais antigas e gerando novo QR automaticamente...');
                try {
                    fs.rmSync(path.join(__dirname, 'auth_smc'), { recursive: true, force: true });
                } catch (e) {
                    console.log(`⚠️ Falha ao limpar pasta de sessão antiga: ${e}`);
                }
                agendarReconexao(2000, 'logout');
            } else {
                // 515 (restart required, NORMAL logo após parear), 428, etc.:
                // apenas reconectar (sem apagar credenciais).
                agendarReconexao(5000, `código ${codigoErro}`);
            }
        }
    });

    // Comandos por mensagem: START (inscreve), STOP (desinscreve) e
    // ACATAR (registra que o trader vai operar o último cenário).
    //
    // ⚠️ CORREÇÃO DO LOOP INFINITO:
    //   1) O robô responde CADA comando com uma confirmação (ex.: "✅ Inscrito!
    //      ...Envie STOP..."). Essas confirmações também chegam de volta neste
    //      handler com fromMe=true. Antes usávamos `texto.includes('STOP')`, então
    //      a própria confirmação "...Envie STOP..." re-disparava STOP, que mandava
    //      outra confirmação com "START", e assim infinitamente — spam que levou o
    //      WhatsApp a derrubar a sessão (código 401).
    //   2) A correção tem DUAS camadas:
    //      a) IGNORAR as mensagens que o próprio robô enviou. Toda confirmação do
    //         robô começa com um emoji de status (✅ 🛑 ℹ️ 👍 🚪) — se a mensagem
    //         for fromMe e começar com um desses, é eco do robô: descartar.
    //      b) Reconhecer comando só por CORRESPONDÊNCIA EXATA (`===`), nunca por
    //         `includes`. Assim uma frase longa jamais é confundida com um comando.
    //
    // Continuamos aceitando comandos com fromMe=true (para o dono operar do próprio
    // número), mas só quando o texto é EXATAMENTE o comando — não uma confirmação.
    const PREFIXOS_CONFIRMACAO_ROBO = ['✅', '🛑', 'ℹ️', '👍', '🚪', '📊', '⚠️',
                                       '🔴', '🟢', '📘', '⏳', '👀', '⚪', '🎯'];

    // Extrai o texto de QUALQUER envelope de mensagem do WhatsApp: texto puro,
    // texto com citação (extendedText), mensagem efêmera/viewOnce e respostas
    // de botão/lista. Sem isso, alguns tipos de mensagem chegam "sem texto" e o
    // comando (START/STOP/ACATAR) nunca é reconhecido.
    const extrairTexto = (message) => {
        if (!message) return "";
        if (message.ephemeralMessage)  return extrairTexto(message.ephemeralMessage.message);
        if (message.viewOnceMessage)   return extrairTexto(message.viewOnceMessage.message);
        if (message.viewOnceMessageV2) return extrairTexto(message.viewOnceMessageV2.message);
        return (message.conversation ||
                message.extendedTextMessage?.text ||
                message.buttonsResponseMessage?.selectedDisplayText ||
                message.listResponseMessage?.title ||
                "");
    };

    // Processa UMA mensagem (um comando). É chamada para CADA mensagem do lote.
    // Antes o handler só olhava m.messages[0]; quando comandos chegavam em lote
    // (ex.: após reconexão, ou várias mensagens juntas), os demais eram
    // ignorados — por isso vários START não vinculavam.
    const processarMensagem = async (msg, tipoUpsert) => {
        if (!msg || !msg.message) return;

        // Colapsa espaços e remove caracteres invisíveis (zero-width) que às
        // vezes vêm junto e quebravam a comparação exata.
        const textoBruto = extrairTexto(msg.message)
            .replace(/[​-‍﻿]/g, '')
            .replace(/\s+/g, ' ')
            .trim();
        if (!textoBruto) return;

        const jidAlvo = msg.key.remoteJid;

        // Log de TODA mensagem recebida — essencial pra diagnosticar comandos.
        console.log(`💬 msg (tipo=${tipoUpsert}, fromMe=${msg.key.fromMe}) ${jidAlvo}: "${textoBruto}"`);

        // Descarta ecos das próprias confirmações do robô (evita o loop).
        if (msg.key.fromMe &&
            PREFIXOS_CONFIRMACAO_ROBO.some((p) => textoBruto.startsWith(p))) {
            return;
        }

        // Normaliza para comparar comando por igualdade exata.
        const texto = textoBruto.toUpperCase();

        // Conjuntos de comandos aceitos (correspondência EXATA — evita o loop).
        const CMD_STOP      = ['STOP', 'PARAR'];
        const CMD_START     = ['START', 'INICIAR', 'INICIO', 'INÍCIO'];
        const CMD_ACATAR    = ['ACATAR', 'ACATEI', 'ACATO', 'ACATAR CENARIO',
                               'ACATAR CENÁRIO', 'SIM'];
        const CMD_DISPENSAR = ['NAO OPEREI', 'NÃO OPEREI', 'DISPENSAR',
                               'NAO ACATAR', 'NÃO ACATAR', 'NAO ACATO', 'NÃO ACATO'];

        const ehComando =
            CMD_STOP.includes(texto) || CMD_START.includes(texto) ||
            CMD_ACATAR.includes(texto) || CMD_DISPENSAR.includes(texto);

        if (!ehComando) return;

        console.log(`✅ Comando reconhecido: "${texto}"`);

        if (CMD_STOP.includes(texto)) {
            const removido = removerInscrito(jidAlvo);
            await sock.sendMessage(jidAlvo, {
                text: removido
                    ? "🛑 Você PAROU de receber os relatórios do Robô SMC neste chat.\nEnvie START para voltar a receber."
                    : "ℹ️ Este chat já não estava recebendo os relatórios."
            });
            return;
        }

        if (CMD_START.includes(texto)) {
            const adicionado = adicionarInscrito(jidAlvo);
            console.log(adicionado
                ? `✅ NOVO contato inscrito via START: ${jidAlvo} (total: ${lerInscritos().length}). Remova no painel se não foi você.`
                : `ℹ️ START em ${jidAlvo}: já estava inscrito (total: ${lerInscritos().length}).`);
            await sock.sendMessage(jidAlvo, {
                text: adicionado
                    ? "✅ Inscrito! Este chat passará a receber os relatórios do Robô SMC.\nEnvie STOP quando quiser parar."
                    : "✅ Este chat JÁ estava recebendo os relatórios do Robô SMC.\nEnvie STOP quando quiser parar."
            });
            return;
        }

        // ACATAR / ACATO / ACATEI -> registra intenção de operar o último
        // cenário sugerido. O app (main_app.py) lê isso via GET /comandos e
        // abre a posição na direção do sinal (mesma lógica do botão "Acatei").
        if (CMD_ACATAR.includes(texto)) {
            filaComandos.push({ tipo: 'ACATAR', jid: jidAlvo, ts: Date.now() });
            await sock.sendMessage(jidAlvo, {
                text: "👍 Recebido: vou registrar o ACATAR do último cenário no seu diário e acompanhar até stop/alvo."
            });
            return;
        }

        // NAO OPEREI / DISPENSAR -> encerra o acompanhamento do último cenário.
        if (CMD_DISPENSAR.includes(texto)) {
            filaComandos.push({ tipo: 'DISPENSAR', jid: jidAlvo, ts: Date.now() });
            await sock.sendMessage(jidAlvo, {
                text: "🚪 Ok: não vou fazer acompanhamento desse cenário."
            });
            return;
        }
    };

    // Percorre TODAS as mensagens do lote (não só a primeira) e processa cada
    // uma com blindagem — um erro em uma não impede as outras.
    sock.ev.on('messages.upsert', async (m) => {
        // Log CRU: prova que o handler está sendo chamado e quantas mensagens
        // chegaram. Se você manda START e ISSO nem aparece, o problema é a
        // entrega do WhatsApp/conexão — não o reconhecimento do comando.
        console.log(`📥 upsert recebido: ${(m.messages || []).length} mensagem(ns), tipo=${m.type}`);
        for (const msg of (m.messages || [])) {
            try {
                await processarMensagem(msg, m.type);
            } catch (e) {
                console.log(`⚠️ Erro ao processar mensagem do lote: ${e}`);
            }
        }
    });

        // Confirmação de que o listener de comandos foi de fato instalado nesta conexão.
        console.log(`🎧 Listener de comandos (START/STOP/ACATAR) instalado. Build: ${MOTOR_BUILD}`);
    } catch (e) {
        console.log(`❌ Falha ao iniciar a conexão do WhatsApp: ${e}`);
        agendarReconexao(5000, 'erro ao conectar');
    } finally {
        // Libera a trava: o socket já foi criado e os listeners registrados.
        conectando = false;
    }
}

// --------------------------------------------------------------------
// Endpoints consultados pela GUI (main_app.py)
// --------------------------------------------------------------------
app.get('/qrcode', (req, res) => {
    res.json({ status: statusConexao, qrCodeBase64: ultimoQrBase64 });
});

app.get('/status', (req, res) => {
    res.json({ status: statusConexao, inscritos: lerInscritos().length });
});

// Lista os inscritos atuais (para o app mostrar/gerenciar).
app.get('/inscritos', (req, res) => {
    res.json({ subscribers: lerInscritos() });
});

// Remove UM inscrito específico (chamado pelo painel do app).
app.post('/remover-inscrito', (req, res) => {
    const { jid } = req.body || {};
    if (!jid) return res.status(400).json({ ok: false, erro: 'Informe o jid.' });
    const removido = removerInscrito(jid);
    console.log(`🗑️ Inscrito removido pelo painel do app: ${jid} `
        + `(${removido ? 'removido' : 'não estava na lista'}).`);
    res.json({ ok: true, removido });
});

// Zera TODA a lista de inscritos (painel do app) — reset limpo.
app.post('/limpar-inscritos', (req, res) => {
    salvarInscritos([]);
    console.log('🧹 Lista de inscritos ZERADA pelo painel do app.');
    res.json({ ok: true });
});

// FORÇA RE-PAREAMENTO (abra http://localhost:3939/reparear no navegador).
// Use quando o WhatsApp aparece "conectado" mas NÃO recebe mensagens (sessão
// meio-morta após vários 401): apaga as credenciais e gera um QR NOVO para
// escanear no app. É o conserto real do "não recebe comando".
app.get('/reparear', async (req, res) => {
    console.log('🔁 Re-pareamento FORÇADO solicitado — limpando sessão...');
    try {
        // Remove os listeners ANTES de encerrar: assim o 'close' do socket velho
        // não dispara outra reconexão (evita a tempestade de QRs). A reconexão é
        // agendada UMA vez, pelo agendarReconexao (que faz dedup).
        if (sock) {
            try { sock.ev.removeAllListeners(); } catch (e) {}
            try { await sock.logout(); } catch (e) { /* já pode estar caído */ }
            try { sock.end(undefined); } catch (e) {}
            sock = null;
        }
        fs.rmSync(path.join(__dirname, 'auth_smc'), { recursive: true, force: true });
        statusConexao = 'AGUARDANDO_QR';
        ultimoQrBase64 = null;
        agendarReconexao(1500, 'reparear');
        res.send('OK — sessão limpa. Volte ao app: um NOVO QR vai aparecer, escaneie-o UMA vez. '
            + 'Depois mande START de novo nos chats desejados.');
    } catch (e) {
        console.log(`⚠️ Falha ao forçar re-pareamento: ${e}`);
        res.status(500).send(String(e));
    }
});

// Fila de comandos recebidos por WhatsApp (ACATAR/DISPENSAR). Devolve e
// LIMPA a fila — o app consome uma vez e age.
app.get('/comandos', (req, res) => {
    const pendentes = filaComandos;
    filaComandos = [];
    res.json({ comandos: pendentes });
});

app.post('/enviar-relatorio', async (req, res) => {
    try {
        // Só envia se o WhatsApp estiver realmente CONECTADO e autenticado.
        // Enviar durante a troca de socket causava "Cannot read ... 'id'".
        if (statusConexao !== 'CONECTADO' || !sock || !sock.user) {
            return res.status(503).send(
                "WhatsApp não está conectado agora — relatório não enviado (será reenviado no próximo ciclo)."
            );
        }

        const { jid, texto, imagemBase64 } = req.body;

        // Se um jid específico foi passado, envia só para ele (compatibilidade).
        // Caso contrário, faz BROADCAST para todos os inscritos.
        const destinos = (jid && jid.trim())
            ? [jid.trim()]
            : lerInscritos();

        if (!destinos.length) {
            return res.status(400).send(
                "Erro: Nenhum contato inscrito. Envie START no WhatsApp a partir do contato/grupo que deve receber os relatórios."
            );
        }

        const buffer = imagemBase64 ? Buffer.from(imagemBase64, 'base64') : null;

        // Envia para todos; coleta falhas sem derrubar o envio dos demais.
        let enviados = 0;
        const falhas = [];
        for (const destino of destinos) {
            try {
                if (buffer) {
                    await sock.sendMessage(destino, { image: buffer, caption: texto });
                } else {
                    await sock.sendMessage(destino, { text: texto });
                }
                enviados++;
            } catch (e) {
                falhas.push(`${destino}: ${e.toString()}`);
            }
        }

        if (enviados === 0) {
            return res.status(500).send(`Falha ao enviar para todos os inscritos. ${falhas.join(' | ')}`);
        }
        // 200 mesmo com falhas parciais: o essencial (ao menos 1 envio) ocorreu.
        res.status(200).send(`OK (${enviados}/${destinos.length} enviados)`);
    } catch (e) {
        res.status(500).send(e.toString());
    }
});

connectToWhatsApp();

const PORTA = 3939;
const servidor = app.listen(PORTA, () => {
    console.log(`🚀 API Gateway rodando na porta ${PORTA}`);
    console.log(`🔧 MOTOR BUILD: ${MOTOR_BUILD}  (se não vir esta linha, é motor ANTIGO)`);
});

servidor.on('error', (erro) => {
    if (erro.code === 'EADDRINUSE') {
        console.log(`❌ ERRO: a porta ${PORTA} já está em uso por outro programa/processo node.exe.`);
        console.log('   Finalize processos node.exe órfãos no Gerenciador de Tarefas e reinicie.');
        process.exit(1);
    } else {
        console.log(`❌ Erro inesperado ao iniciar o servidor: ${erro.message}`);
        process.exit(1);
    }
});
