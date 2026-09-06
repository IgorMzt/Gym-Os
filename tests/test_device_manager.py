import unittest
import device_manager


class DeviceManagerTests(unittest.TestCase):
    def test_modo_simulado(self):
        resposta = device_manager.acionar({"id": 1, "modo": "SIMULADA", "ativa": True})
        self.assertTrue(resposta["sucesso"])
        self.assertEqual(resposta["modo"], "SIMULADA")

    def test_hardware_nao_configurado_falha_fechado(self):
        with self.assertRaises(device_manager.DeviceError):
            device_manager.acionar({"id": 1, "modo": "HTTP", "ativa": True})

    def test_catraca_inativa(self):
        with self.assertRaises(device_manager.DeviceError):
            device_manager.acionar({"id": 1, "modo": "SIMULADA", "ativa": False})


if __name__ == "__main__":
    unittest.main()
