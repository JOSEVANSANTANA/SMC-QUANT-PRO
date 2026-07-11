// ============================================================
// SMC QUANT PRO — Servidor de Licenças (TIGER INVEST VIP)
// ============================================================
// O que ele faz:
//   • Guarda as chaves de licença que VOCÊ cria
//   • Na primeira ativação, "casa" a chave com o ID de UMA máquina
//   • Se a mesma chave tentar ativar em outra máquina, recusa
//   • Registra cada ativação (chave, máquina, data) — é a sua LISTA
//   • Permite revogar uma chave remotamente
//
// Banco de dados: um arquivo JSON simples (licencas.json). Para começar é
// suficiente. Se um dia crescer muito, migra-se para um banco de verdade.
// ============================================================

const express = require("express");
const cors = require("cors");
const fs = require("fs");
const path = require("path");

const app = express();
app.use(cors());          // libera o painel (rodando localmente) a chamar o servidor
app.use(express.json());

const DB = path.join(__dirname, "licencas.json");

// Senha de administrador — troque por algo forte e NUNCA compartilhe.
// É o que protege o seu painel de quem pode criar/revogar chaves.
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || "TROQUE-ESTA-SENHA-AGORA";

// ---------- utilidades de banco ----------
function lerDB() {
  try {
    return JSON.parse(fs.readFileSync(DB, "utf-8"));
  } catch {
    return { licencas: {} };
  }
}
function salvarDB(dados) {
  fs.writeFileSync(DB, JSON.stringify(dados, null, 2));
}

// Middleware simples de admin: exige o token no cabeçalho.
function exigirAdmin(req, res, next) {
  if (req.headers["x-admin-token"] !== ADMIN_TOKEN) {
    return res.status(401).json({ ok: false, erro: "Não autorizado." });
  }
  next();
}

// ============================================================
// ROTA 1 — ATIVAÇÃO (chamada pelo app do cliente)
// ============================================================
app.post("/ativar", (req, res) => {
  const { chave, maquina_id, nome_maquina } = req.body || {};
  if (!chave || !maquina_id) {
    return res.status(400).json({ ok: false, erro: "Dados incompletos." });
  }

  const db = lerDB();
  const lic = db.licencas[chave];

  // Chave não existe
  if (!lic) {
    return res.json({ ok: false, erro: "Chave de licença inválida." });
  }
  // Chave revogada por você
  if (lic.revogada) {
    return res.json({ ok: false, erro: "Esta licença foi desativada. Contate o suporte." });
  }
  // Chave já casada com OUTRA máquina (regra: 1 máquina por chave)
  if (lic.maquina_id && lic.maquina_id !== maquina_id) {
    return res.json({
      ok: false,
      erro: "Esta chave já está em uso em outro computador. Cada licença vale para 1 máquina.",
    });
  }

  // Primeira ativação: casa a chave com esta máquina e registra.
  if (!lic.maquina_id) {
    lic.maquina_id = maquina_id;
    lic.nome_maquina = nome_maquina || "desconhecida";
    lic.ativada_em = new Date().toISOString();
  }
  lic.ultimo_acesso = new Date().toISOString();
  salvarDB(db);

  return res.json({ ok: true, mensagem: "Licença ativada com sucesso.", validade: lic.validade || null });
});

// ============================================================
// ROTA 2 — REVALIDAÇÃO (o app confere de tempos em tempos)
// ============================================================
app.post("/validar", (req, res) => {
  const { chave, maquina_id } = req.body || {};
  const db = lerDB();
  const lic = db.licencas[chave];
  if (!lic || lic.revogada || lic.maquina_id !== maquina_id) {
    return res.json({ ok: false });
  }
  lic.ultimo_acesso = new Date().toISOString();
  salvarDB(db);
  return res.json({ ok: true });
});

// ============================================================
// ROTAS DE ADMIN (só você, com o token)
// ============================================================

// Criar uma nova chave
app.post("/admin/criar", exigirAdmin, (req, res) => {
  const { chave, cliente } = req.body || {};
  if (!chave) return res.status(400).json({ ok: false, erro: "Informe a chave." });
  const db = lerDB();
  if (db.licencas[chave]) return res.json({ ok: false, erro: "Chave já existe." });
  db.licencas[chave] = {
    cliente: cliente || "",
    criada_em: new Date().toISOString(),
    maquina_id: null,
    nome_maquina: null,
    ativada_em: null,
    ultimo_acesso: null,
    revogada: false,
  };
  salvarDB(db);
  res.json({ ok: true, mensagem: "Chave criada.", chave });
});

// Revogar uma chave (desativa remotamente)
app.post("/admin/revogar", exigirAdmin, (req, res) => {
  const { chave } = req.body || {};
  const db = lerDB();
  if (!db.licencas[chave]) return res.json({ ok: false, erro: "Chave não encontrada." });
  db.licencas[chave].revogada = true;
  salvarDB(db);
  res.json({ ok: true, mensagem: "Chave revogada." });
});

// Liberar a chave de uma máquina (ex: cliente trocou de PC)
app.post("/admin/liberar", exigirAdmin, (req, res) => {
  const { chave } = req.body || {};
  const db = lerDB();
  if (!db.licencas[chave]) return res.json({ ok: false, erro: "Chave não encontrada." });
  db.licencas[chave].maquina_id = null;
  db.licencas[chave].nome_maquina = null;
  db.licencas[chave].ativada_em = null;
  salvarDB(db);
  res.json({ ok: true, mensagem: "Máquina liberada — a chave pode ser reativada em outro PC." });
});

// SUA LISTA: todas as licenças e ativações
app.get("/admin/lista", exigirAdmin, (req, res) => {
  const db = lerDB();
  const lista = Object.entries(db.licencas).map(([chave, l]) => ({
    chave,
    cliente: l.cliente,
    status: l.revogada ? "REVOGADA" : (l.maquina_id ? "ATIVA" : "NÃO ATIVADA"),
    nome_maquina: l.nome_maquina,
    ativada_em: l.ativada_em,
    ultimo_acesso: l.ultimo_acesso,
  }));
  res.json({ ok: true, total: lista.length, licencas: lista });
});

// Página de saúde (para o Render saber que está no ar)
app.get("/", (req, res) => res.send("SMC Quant Pro — Servidor de Licenças ativo."));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Servidor de licenças rodando na porta ${PORT}`));
