const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const pino = require('pino');
const express = require('express');
const cors = require('cors');
const QRCode = require('qrcode');
const fs = require('fs');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json({ limit: '50mb' }));

let sock;
let ultimoQrBase64 = null;              // "data:image/png;base64,...." pronto para <img src="...">
let statusConexao = 'AGUARDANDO_QR';    // AGUARDANDO_QR | CONECTADO | DESCONECTADO

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

    // Migração automática do formato antigo (registered_jid.json com 1 JID).
    try {
        const antigo = JSON.parse(fs.readFileSync(caminhoConfigJidAntigo, 'utf8'));
        if (antigo.registered_jid) {
            const lista = [antigo.registered_jid];
            salvarInscritos(lista);
            console.log(`♻️ Migrado o contato antigo para a nova lista de inscritos: ${antigo.registered_jid}`);
            return lista;
        }
    } catch (e) { /* sem legado */ }

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
                setTimeout(connectToWhatsApp, 2000);
            } else {
                setTimeout(connectToWhatsApp, 5000); // espera 5s — evita martelar o WhatsApp em loop agressivo
            }
        }
    });

    // Comandos por mensagem: START (inscreve), STOP (desinscreve) e
    // ACATAR (registra que o trader vai operar o último cenário).
    // Sem checar fromMe: se o comando vier do mesmo número logado no bot,
    // a mensagem chega com fromMe=true — sem essa flexibilidade, o comando
    // nunca seria capturado nesse cenário.
    sock.ev.on('messages.upsert', async (m) => {
        const msg = m.messages[0];
        if (!msg.message) return;

        const texto = (msg.message.conversation ||
                       msg.message.extendedTextMessage?.text ||
                       "").trim().toUpperCase();
        if (!texto) return;

        const jidAlvo = msg.key.remoteJid;
        console.log(`💬 Mensagem recebida (fromMe=${msg.key.fromMe}) em ${jidAlvo}: "${texto}"`);

        // STOP é checado ANTES de START (a palavra "START" nunca contém "STOP",
        // mas mantemos a ordem explícita para clareza).
        if (texto.includes('STOP')) {
            const removido = removerInscrito(jidAlvo);
            await sock.sendMessage(jidAlvo, {
                text: removido
                    ? "🛑 Você PAROU de receber os relatórios do Robô SMC neste chat.\nEnvie START para voltar a receber."
                    : "ℹ️ Este chat já não estava recebendo os relatórios."
            });
            return;
        }

        if (texto.includes('START')) {
            const adicionado = adicionarInscrito(jidAlvo);
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
        if (texto.includes('ACATAR') || texto.includes('ACATEI') || texto.includes('ACATO')) {
            filaComandos.push({ tipo: 'ACATAR', jid: jidAlvo, ts: Date.now() });
            await sock.sendMessage(jidAlvo, {
                text: "👍 Recebido: vou registrar o ACATAR do último cenário no seu diário e acompanhar até stop/alvo."
            });
            return;
        }

        // NAO OPEREI / DISPENSAR -> encerra o acompanhamento do último cenário.
        if (texto.includes('NAO OPEREI') || texto.includes('NÃO OPEREI') || texto.includes('DISPENSAR')) {
            filaComandos.push({ tipo: 'DISPENSAR', jid: jidAlvo, ts: Date.now() });
            await sock.sendMessage(jidAlvo, {
                text: "🚪 Ok: não vou fazer acompanhamento desse cenário."
            });
            return;
        }
    });
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

// Lista os inscritos atuais (para o app mostrar/gerenciar, se quiser).
app.get('/inscritos', (req, res) => {
    res.json({ subscribers: lerInscritos() });
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
const servidor = app.listen(PORTA, () => console.log(`🚀 API Gateway rodando na porta ${PORTA}`));

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
