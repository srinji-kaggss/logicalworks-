import unittest
from lgwks_keyvault import get_secret, is_configured

class TestLgwksKeyvault(unittest.TestCase):
    
    def test_get_secret_nonexistent(self):
        # Call get_secret with a secret that does not exist
        result = get_secret('LGWKS_TEST_SECRET_DOES_NOT_EXIST_12345')
        # Assert that it does not raise and returns None as first element
        self.assertIsNone(result[0])
        
    def test_is_configured_nonexistent(self):
        # Call is_configured with a secret that does not exist
        result = is_configured('LGWKS_TEST_SECRET_DOES_NOT_EXIST_12345')
        # Assert that it returns False
        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()