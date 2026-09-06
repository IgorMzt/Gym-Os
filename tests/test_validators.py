import unittest
from validators import cpf_valido, email_valido, parse_bool, parse_int


class ValidatorTests(unittest.TestCase):
    def test_cpf_valido(self):
        self.assertTrue(cpf_valido("529.982.247-25"))
        self.assertFalse(cpf_valido("111.111.111-11"))
        self.assertFalse(cpf_valido("123"))

    def test_booleanos_textuais(self):
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("sim"))
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("0"))
        with self.assertRaises(ValueError):
            parse_bool("talvez")

    def test_inteiro_com_limites(self):
        self.assertEqual(parse_int("850", "Intervalo", 500, 5000), 850)
        with self.assertRaises(ValueError):
            parse_int("100", "Intervalo", 500, 5000)

    def test_email(self):
        self.assertTrue(email_valido("aluno@exemplo.com"))
        self.assertTrue(email_valido(None))
        self.assertFalse(email_valido("aluno@"))


if __name__ == "__main__":
    unittest.main()
