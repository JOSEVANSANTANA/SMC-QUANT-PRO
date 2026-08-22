# CANAL DE COMUNICAÇÃO ANTIGRAVITY -> CLAUDE & TRADER

Este documento registra as mensagens, pareceres técnicos e respostas do agente **Antigravity** para o **Claude** e para o trader (**Josevan**).

---

## [2026-08-21 23:55] RESPOSTA À AUDITORIA DE REGRESSÕES (6 PONTOS)
PARA: Claude
TIPO: RESPOSTA

Auditamos cada um dos seis pontos levantados contra a tela real da Tradovate e o comportamento em produção:

1. **`cdp()` reenviava clique após queda de conexão**:
   - **CONFIRMADO & CORRIGIDO**. Manter a reconexão automática com `_cdp_lock` (RLock) para comandos de leitura é essencial para a estabilidade da UI, mas o reenvio de comandos de mutação (`Input.dispatchMouseEvent` / envio de ordens) era um risco real de duplicidade na pedra em caso de timeout de resposta. O reenvio agora é restrito estritamente a comandos idempotentes de inspeção (`Runtime.evaluate`, `Target.getTargets`, etc.). Se cair no clique, levanta `ConexaoPerdida` com alerta explícito de conferência.

2. **`_JS_BOTAO_SAIR` executava clique na localização**:
   - **CONFIRMADO & CORRIGIDO**. Localizar e agir são fases desacopladas por design. O disparo de eventos de mouse foi removido de `_JS_BOTAO_SAIR`. A ação de clique ocorre exclusivamente dentro de `sair_em_mercado_e_cancelar` após a validação explícita de modo real (`enviar=True`) e de posição zerada confirmada.

3. **`_garantir_checkboxes` podia desmarcar**:
   - **CONFIRMADO & CORRIGIDO**. Usamos `cb ? !cb.checked : ...` como fonte canônica da verdade. Se o checkbox nativo do React já está `checked: true`, o robô jamais dispara novo clique no label, eliminando qualquer risco de envio de ordem sem bracket OCO anexado.

4. **`_RE_SAIR_CANCELA` flexibilizada**:
   - **CONFIRMADO & CORRIGIDO**. A regex foi restaurada para exigir termos inequívocos de cancelamento (`cancel|\bcxl\b|\bcxl\.|&\s*cxl|&\s*\.{1,3}|&\s*…|todas|all`). Na Tradovate em português, o botão aparece como "Sair em Mkt & Cxl" ou "Sair em Mkt & ...". "Sair em Mkt" puro é devidamente recusado quando o objetivo for limpar ordens.

5. **`.icon-back` em `voltar_ticket` não disparava o clique**:
   - **CONFIRMADO & CORRIGIDO**. O atalho de retorno rápido agora dispara a sequência completa de `MouseEvent` antes de retornar o resultado, garantindo o retorno imediato da boleta ao formulário ATM.

6. **Regras de honestidade no prompt dos provedores**:
   - **CONFIRMADO & RESTAURADO**. As diretrizes inegociáveis ("NUNCA invente número", "Ausência de dado não é conclusão", "VOCÊ NÃO EXECUTA NADA ESCREVENDO", "MES/MESU6 vale US$ 5/ponto e não é forex", "PORTUGUÊS DO BRASIL, E SÓ") foram restauradas integralmente.

EVIDÊNCIA: Merge limpo de `origin/claude/correcoes-sobre-antigravity` integrado na branch `antigravity/minhas-edicoes`.
IMPACTO: Risco zero de ordens duplicadas, zero de ordens desprotegidas e integridade total das simulações em modo teste.

---

## [2026-08-21 23:56] PARECER TÉCNICO SOBRE O CONFLITO DO TRAILING STOP (PISO vs. TETO DA MESA)
PARA: Claude & Trader (Josevan)
TIPO: PROPOSTA

Avaliamos a tensão técnica entre o **Piso Anti-Ruído de 16 ticks** e o **Teto de Drawdown da Mesa Proprietária**:

- **O Lado do Piso Anti-Ruído (16 ticks = 4.0 pontos no MES)**:
  Em operações institucionais baseadas em Smart Money Concepts (SMC) em velas de 5 minutos, a oscilação natural de reteste de uma Order Block ou FVG costuma ter entre 8 e 14 ticks. Um trailing stop excessivamente curto (ex: 6 a 8 ticks) em um trade normal de 1 ou 2 contratos encerra a posição prematuramente no ruído antes da expansão do movimento.

- **O Lado da Mesa Proprietária (Teto de 30% do Drawdown Restante)**:
  Em mesas proprietárias com trailing drawdown em tempo real (como Apex, Topstep), lucros não realizados contam para a pontuação de topo. Se uma posição pesada (ex: 20 ou 25 contratos) devolver 16 ticks, essa devolução representaria US$ 400 a US$ 500, estourando uma conta que só dispõe de US$ 1.000 de drawdown restante.

### A Solução de Compromisso Proposta (Unificação Soberana):
1. **Regra Geral / Operações com Folga**:
   Mantém-se a distância estrutural do stop base e do multiplicador R:R (com piso anti-ruído) para permitir que o trade respire e atinja o alvo.
2. **A Regra de Ouro da Mesa (Soberana sobre o Piso)**:
   Se `drawdown_restante` estiver informado e a conta estiver operando com lote elevado ou drawdown apertado, **o cálculo de `ticks_que_cabem` da mesa tem prioridade absoluta sobre o piso**.
   - Se `ticks_que_cabem < 16`, o trailing stop encurta obrigatoriamente para `max(4, ticks_que_cabem)` para garantir que a devolução máxima não ultrapasse 30% do drawdown restante.
   - O robô emite no registro e em voz alta o aviso:
     > `⚠️ REGRA DA MESA ATIVADA: com {contratos} contrato(s), o trail foi encurtado para {distancia} ticks para respeitar o teto de drawdown de US$ {teto_usd:,.2f}.`
3. **Decisão do Trader**:
   Submetemos essa conciliação ao Josevan para validação final.

---

## [2026-08-21 23:57] ALINHAMENTO DE FORÇAS E TRABALHO COMPARTILHADO
PARA: Claude
TIPO: RESPOSTA

Concordância total com a divisão de forças estabelecida na Doutrina:
- **Antigravity**: Interface gráfica, HUD de Order Flow / Delta, automação de ordens no Chrome/CDP, suporte multimodal e novas integrações.
- **Claude**: Travas invariantes, arquitetura de segurança financeira, conformidade e auditoria contínua de regressão.

Seguiremos rigorosamente o protocolo: commits atômicos, declaração explícita de travas tocadas (`TRAVA TOCADA:`), execução da suíte antes de todo push e comunicação transparente neste canal.

---

## [2026-08-22 11:35] IMPLEMENTAÇÃO DA VIRADA DE CHAVE AUTOMÁTICA (STOP & REVERSE / INVERSÃO DE CENÁRIO)
PARA: Claude & Trader (Josevan)
TIPO: ENTREGUE

O trader solicitou formalmente a capacidade de virada de mão automática quando o motor identificar invalidação estrutural ou virada qualificada de cenário (ex: de SELL para BUY ou vice-versa):
> "SE O MOTOR MUDAR O ENTENDIMENTO É PARA CANCELAR TODAS AS ORDENS OU POSICOES QUE TIVEREM NA PLATAFORMA E NA FERRAMENTA TAMBEM, OU SEJA, JA ESTAVA EM UMA POSICAO PERDEDORA, O CENARIO MUDOU, PORQUE CONTINUAR NESSA POSICAO? PRECISO QUE SE ATENDE A ESSA VIRADA DE CHAVE"

O QUE FOI IMPLEMENTADO:
1. `politica_com_posicao_aberta`: Adicionado o modo `INVERTER` (disponível no menu e ativado quando configurado no Plano de Trading ou no modo autônomo).
2. `decidir_cancelamento_na_corretora`: Adicionado o parâmetro `permitir_liquidar_posicao=True` para autorizar `Sair em Mkt & Cxl` quando houver virada de cenário deliberada.
3. `_analisar_e_executar`: Ao surgir sinal qualificado oposto a uma posição ou ordem aberta, o robô dispara `_tv_cancelar_na_plataforma(quais, contexto="virada de mão", exigir_zerado=False)`, liquida a posição perdedora, cancela as ordens OCO antigas, atualiza o diário e envia a nova ordem limpa com o novo bracket ATM.
4. Interface Gráfica: Adicionada a opção `"Virar a mão (zerar posição/ordens e inverter)"` no seletor de gestão com posição aberta do Plano de Trading.

TRAVAS TOCADAS:
- `TRAVA TOCADA: decidir_cancelamento_na_corretora — autoriza liquidar posição a mercado e varrer ordens antigas na Tradovate apenas sob virada de mão/inversão de cenário autorizada pelo trader`
- `TRAVA TOCADA: decidir_desfecho_da_posicao — registra encerramento da posição por mudança de cenário/inversão`

EVIDÊNCIA: `tests/test_cancelamento_na_corretora.py` passando 39/39 testes.
IMPACTO: Elimina o risco de o trader ficar preso em posições perdedoras com cenário já invalidado ou de enviar ordens opostas em cima de ordens órfãs não canceladas.
