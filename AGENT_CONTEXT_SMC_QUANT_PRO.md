# Contexto do projeto SMC Quant Pro

## Data
2026-09-30

## Alinhamento da conversa
- A base do projeto local e do GitHub deve permanecer sincronizada.
- Mudanças técnicas fundamentais podem ser aplicadas com autonomia, desde que o repositório esteja aberto, a branch correta esteja ativa e a alteração não seja destrutiva.
- Antes de mudanças de comportamento crítico, dependências ou deploy, o usuário será alertado e a decisão será explicitada.
- O objetivo final da ferramenta é manter a operação estável, reduzir gargalos e corrigir erros sem perder a lógica de negócio da estratégia.
- O projeto já foi publicado na branch feature/update-v2-85 no GitHub.
- A IA usada para implementar e alterar código neste contexto é GitHub Copilot com o modelo MAI-Code-1.1-Flash.

## Regras operacionais
1. O repositório local e o GitHub devem ficar sincronizados.
2. Mudanças críticas podem ser aplicadas com autonomia quando forem necessárias para manter a ferramenta funcional e alinhada ao objetivo final.
3. Mudanças de comportamento externo, dependências ou execução de produção devem ser comunicadas antes da execução.
4. O agente de monitoramento deve observar logs, gargalos, latência, falhas e comportamento operacional.
5. Quando um erro for identificado, o agente deve priorizar correções que preservem a lógica de negócio e a finalidade da ferramenta.

## Repositório
- Nome local: SMC_QUANT_PRO
- Repositório remoto: SMC-QUANT-PRO
- Branch ativa: feature/update-v2-85

## Próximo passo sugerido
Construir um agente de monitoramento em tempo real para:
- observar logs e indicadores de desempenho;
- detectar falhas, gargalos e exceções;
- priorizar correções alinhadas ao objetivo final da ferramenta;
- aplicar ajustes automáticos quando a correção for segura e diretamente ligada ao propósito do sistema.
