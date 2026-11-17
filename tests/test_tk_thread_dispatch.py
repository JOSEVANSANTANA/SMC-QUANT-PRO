import ast
import os
import unittest

from harness import RAIZ


with open(os.path.join(RAIZ, "main_app.py"), encoding="utf-8") as arquivo:
    ARVORE = ast.parse(arquivo.read())

APP = next(
    no for no in ARVORE.body
    if isinstance(no, ast.ClassDef) and no.name == "SmcQuantApp"
)
METODOS = {
    no.name: no for no in APP.body if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
}


class TestDespachoDaInterfaceTk(unittest.TestCase):

    def test_after_de_worker_entra_na_fila_e_o_dispatcher_roda_no_tk(self):
        metodo = METODOS["after"]
        chamadas = [no for no in ast.walk(metodo) if isinstance(no, ast.Call)]
        atributos = {
            no.func.attr for no in chamadas if isinstance(no.func, ast.Attribute)
        }
        self.assertIn("put", atributos)
        self.assertIn("after", atributos)

        dispatcher = METODOS["_drain_ui_tasks"]
        chamadas_dispatcher = [
            no for no in ast.walk(dispatcher) if isinstance(no, ast.Call)
        ]
        self.assertTrue(any(
            isinstance(no.func, ast.Attribute) and no.func.attr == "get_nowait"
            for no in chamadas_dispatcher
        ))
        self.assertTrue(any(
            isinstance(no.func, ast.Attribute) and no.func.attr == "after"
            for no in chamadas_dispatcher
        ))

    def test_workers_de_trading_nao_leem_booleanvar(self):
        workers = (
            "_plataforma_confirma_fills",
            "_modo_autonomo",
            "_acatar_sozinha",
            "_resolver_ordens_orfas_na_corretora",
            "_tv_enviar_bracket",
            "_loop_robo_quant",
        )
        variaveis_tk = {
            "tv_auto_var", "tv_dry_var", "tv_sync_var",
            "tv_cancelar_var", "tv_trail_var",
        }
        acessos = []
        for nome in workers:
            for no in ast.walk(METODOS[nome]):
                if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
                    continue
                alvo = no.func.value
                if (no.func.attr == "get" and isinstance(alvo, ast.Attribute)
                        and alvo.attr in variaveis_tk):
                    acessos.append((nome, alvo.attr, no.lineno))
        self.assertEqual(acessos, [])

    def test_init_continua_montando_a_interface_depois_do_estado_inicial(self):
        inicializador = METODOS["__init__"]
        chamadas = [
            no for no in ast.walk(inicializador)
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
        ]
        self.assertTrue(any(no.func.attr == "_montar_tab_motor" for no in chamadas))


if __name__ == "__main__":
    unittest.main(verbosity=2)