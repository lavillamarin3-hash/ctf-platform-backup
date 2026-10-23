import unittest
from app.services.kali_instructions import update_text


class KaliInstructionTests(unittest.TestCase):
    def test_replaces_legacy_download_steps_without_changing_tutor_objective(self):
        objective = 'Mi objetivo personalizado. Consulta /practice/evidence.txt.'
        source = ('Inicia una corrida y descarga el ZIP. Extrae los archivos y lee README.txt. '
                  + objective + ' Usa herramientas locales; no necesitas una VM ni contactar hosts.')
        result = update_text(source)
        self.assertIn(objective, result)
        self.assertNotIn('descarga el ZIP', result)
        self.assertIn('terminal de Kali', result)
        self.assertEqual(update_text(result), result)

    def test_custom_instructions_are_unchanged(self):
        self.assertEqual(update_text('Adquiere los registros con curl desde Kali.'),
                         'Adquiere los registros con curl desde Kali.')
        self.assertIsNone(update_text(None))
