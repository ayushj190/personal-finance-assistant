from pathlib import Path
import tempfile
import unittest

from services import secrets_vault


class TestSecretsVault(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_path = Path(self.temp_dir.name) / "vault.bin"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_vault_roundtrip_and_large_pem(self):
        # 1. Simple key
        secrets_vault.put("test_key", "secret_value_123", vault_path=self.vault_path)
        val = secrets_vault.get("test_key", vault_path=self.vault_path)
        self.assertEqual(val, "secret_value_123")

        # 2. Large 4KB RSA PEM key
        large_pem = "-----BEGIN RSA PRIVATE KEY-----\n" + ("MIIEowIBAAKCAQEA0" * 200) + "\n-----END RSA PRIVATE KEY-----"
        secrets_vault.put("large_pem", large_pem, vault_path=self.vault_path)
        pem_back = secrets_vault.get("large_pem", vault_path=self.vault_path)
        self.assertEqual(pem_back, large_pem)

        # 3. Delete
        secrets_vault.delete("test_key", vault_path=self.vault_path)
        self.assertIsNone(secrets_vault.get("test_key", vault_path=self.vault_path))


if __name__ == "__main__":
    unittest.main()
