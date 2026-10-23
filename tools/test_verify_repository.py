"""Pruebas del verificador con archivos temporales, sin credenciales reales."""
import tempfile
import unittest
from pathlib import Path

from verify_repository import verify


class RepositoryChecks(unittest.TestCase):
    def test_sources_and_example_configuration_are_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'main.py').write_text('VALUE = 1\n', encoding='utf-8')
            (root / '.env.example').write_text('API_KEY=DEFINIR_CLAVE_LOCAL\n', encoding='utf-8')
            self.assertEqual(verify(root), (2, 0))

    def test_private_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'secrets.h').write_text('// Configuracion privada de prueba\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Configuracion privada'):
                verify(root)

    def test_token_pattern_is_rejected_without_disclosing_value(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            token = 'ghp_' + 'A' * 36
            (root / 'config.txt').write_text(token, encoding='utf-8')
            with self.assertRaises(ValueError) as caught:
                verify(root)
            self.assertIn('Posible credencial', str(caught.exception))
            self.assertNotIn(token, str(caught.exception))

    def test_broken_documentation_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'README.md').write_text('[Manual](missing.md)', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Enlace local inexistente'):
                verify(root)

    def test_invalid_python_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'main.py').write_text('def broken(\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Error de Python'):
                verify(root)

    def test_binary_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'example.pkl').write_bytes(b'not-a-model')
            with self.assertRaisesRegex(ValueError, 'Archivo no publicable'):
                verify(root)


if __name__ == '__main__':
    unittest.main()
