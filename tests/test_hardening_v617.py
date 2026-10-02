import unittest
from services import security_service
from core.settings import Settings

class HardeningV617Tests(unittest.TestCase):
    def setUp(self): security_service.reset_for_tests()
    def test_rate_limit_bloqueia_excesso(self):
        self.assertTrue(security_service.allow('x',2,60)); self.assertTrue(security_service.allow('x',2,60)); self.assertFalse(security_service.allow('x',2,60))
    def test_rate_limit_isola_chaves(self):
        self.assertTrue(security_service.allow('a',1,60)); self.assertFalse(security_service.allow('a',1,60)); self.assertTrue(security_service.allow('b',1,60))
    def test_versao_617(self): self.assertEqual(Settings.__dataclass_fields__['app_version'].default,'6.17')

if __name__=='__main__': unittest.main()
