# -*- coding: utf-8 -*-
"""
tiger_autonomia.py — O Firewall Cognitivo e Módulo de Sandboxing da TIGER.

Aqui transformamos "bater papo com LLM" em "Agentic Tool Use" determinístico.
O LLM traduz a intenção humana para JSON usando o CASCADE ENGINE (Garante 
resposta mesmo se a Gemini cair). Este módulo valida o JSON e aplica nos 
arquivos do sistema, garantindo que a IA nunca quebre o código fonte.
"""

import json
import logging

class TigerAutonomia:
    def __init__(self, assistente_voz):
        """
        Recebe a instância da TIGER Voice, que contém o método 'consultar_ia_com_fallback',
        garantindo que as alterações passem pela cascata de sobrevivência.
        """
        self.log = logging.getLogger(__name__)
        self.assistente = assistente_voz

        # CAIXA DE AREIA (SANDBOX): Limites rígidos.
        self.TRAVAS_DE_SEGURANCA = {
            "risco_pct": (0.1, 15.0), # Nunca arriscar mais de 15%
            "max_stops_seguidos": (1, 6),
            "probabilidade_minima": (50, 95),
            "rr_minimo": (1.0, 10.0)
        }

    def _prompt_sistemico_json(self, estado_atual):
        return f"""
        Você é o "Agent Router" do SMC Quant Pro. Sua ÚNICA função é traduzir
        a intenção do trader em um arquivo de configuração JSON estrito.
        
        Estado Atual do Plano:
        {json.dumps(estado_atual, indent=2)}
        
        Ação solicitada: Altere apenas os campos que o usuário explicitamente pediu.
        
        REGRA DE SAÍDA OBRIGATÓRIA: Responda APENAS com um JSON Válido. 
        Nenhuma palavra antes ou depois.
        
        Formato Exigido:
        {{
            "sucesso": true/false,
            "alteracoes": [
               {{"campo": "nome_exato", "novo_valor": 12.3}}
            ],
            "resposta_vocal": "Frase curta e objetiva, confirmando a alteração."
        }}
        """

    def processar_comando_sistema(self, texto_falado, estado_do_plano):
        """
        Recebe a intenção, envia pro Cascade Engine exigindo JSON, valida e retorna
        o estado alterado e a frase determinística.
        """
        self.log.info(f"⚡ [Autonomia TIGER] Tentativa de alteração de sistema detectada.")
        
        prompt = self._prompt_sistemico_json(estado_do_plano)
        
        try:
            # Chama o LLM via Cascata forçando o Modo JSON (Sem alucinação)
            resposta_bruta = self.assistente.consultar_ia_com_fallback(
                mensagem_usuario=texto_falado,
                prompt_customizado=prompt,
                json_mode=True
            )
            
            # Limpa lixo de markdown (
```json ... ```) caso o modelo perca o formato
            limpo = resposta_bruta.replace("
```json", "").replace("```", "").strip()
            decisao_llm = json.loads(limpo)
            
        except json.JSONDecodeError:
            self.log.error(f"Alucinação de Formato. Resposta não foi JSON: {resposta_bruta}")
            return {"ok": False, "msg_vocal": "Houve uma falha de tradução sistêmica. Ação abortada para proteger a conta."}
        except Exception as e:
             return {"ok": False, "msg_vocal": f"Erro grave nos provedores: {e}"}

        if not decisao_llm.get("sucesso", False):
            return {"ok": False, "msg_vocal": decisao_llm.get("resposta_vocal", "Comando de alteração recusado por incoerência técnica.")}

        alteracoes_aceitas = 0
        alteracoes_propostas = decisao_llm.get("alteracoes", [])
        
        for alt in alteracoes_propostas:
            campo = alt.get("campo")
            valor = alt.get("novo_valor")
            
            # Validação Hard-Coded (Sandbox)
            if campo in self.TRAVAS_DE_SEGURANCA:
                minimo, maximo = self.TRAVAS_DE_SEGURANCA[campo]
                if isinstance(valor, (int, float)):
                    if minimo <= valor <= maximo:
                        estado_do_plano[campo] = valor
                        alteracoes_aceitas += 1
                    else:
                        self.log.warning(f"Travado: Risco {campo} para {valor} (limites: {minimo}-{maximo})")
                        return {"ok": False, "msg_vocal": f"Tentativa de risco barrada. O valor de {campo} fere as travas institucionais."}
            else:
                 self.log.warning(f"Travado: IA tentou alterar campo bloqueado: {campo}")

        if alteracoes_aceitas > 0:
            msg_final = decisao_llm.get("resposta_vocal", "Parâmetros atualizados no núcleo.")
            self.log.info(f"✅ [Autonomia TIGER] Alterações aplicadas: {alteracoes_propostas}")
            return {"ok": True, "novo_estado": estado_do_plano, "msg_vocal": msg_final}
            
        return {"ok": False, "msg_vocal": "Nenhuma alteração segura encontrada na sua instrução."}