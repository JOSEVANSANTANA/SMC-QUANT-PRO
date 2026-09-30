# SMC Quant Pro - Atualização de release

## Versão: 2.85.0

### O que era antes
A base anterior do projeto já contemplava a versão 2.2.0 com a estrutura inicial do assistente, integração com a plataforma e suporte a anexos básicos. A evolução local trouxe refinamentos importantes na confiabilidade do processamento e na qualidade das respostas.

### O que foi incluído nesta atualização
- correção de erro de leitura de ticker e validação do ativo antes do dimensionamento
- reforço na identificação de inconsistências entre ticker da imagem e instrumento da plataforma
- melhoria na qualidade e legibilidade dos relatórios enviados para o WhatsApp
- segmentação de mensagens em blocos que preservam sentido e evitam cortes no meio da frase
- proteção contra dimensionamento incorreto por letras trocadas no símbolo
- suporte a anexos de imagem, vídeo, PDFs e planilhas com análise mais robusta
- atualização de mensagens de diagnóstico para maior transparência da IA sobre o que foi ouvido e lido
- ajustes na experiência do bot e na gestão de microfone, voz e leitura do ambiente

### Observações
Esta atualização tem foco em confiabilidade operacional e robustez de leitura, reduzindo erros de interpretação e evitando decisões de risco baseadas em ativos incorretos.

### Contexto de branch
A branch local foi desenvolvida como evolução contínua a partir do estado publicado em 2.2.0 no repositório remoto, preservando a base existente e ampliando a lógica de análise, validação e observabilidade.
