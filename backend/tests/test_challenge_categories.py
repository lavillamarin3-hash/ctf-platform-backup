"""Las categorías nuevas usan el campo existente sin permitir nombres inseguros."""
import unittest

from pydantic import ValidationError

from app.schemas import ChallengeCreate


def challenge_with_category(category: str) -> ChallengeCreate:
    return ChallengeCreate(
        code="RED-01",
        name="Reconocimiento controlado",
        description="Ejercicio de reconocimiento en el laboratorio.",
        difficulty="Básico",
        category=category,
        mitre_technique="T1046",
        asset_references=["LAB-01"],
        points=100,
    )


class ChallengeCategoryTests(unittest.TestCase):
    def test_custom_category_is_normalized(self):
        self.assertEqual(challenge_with_category("  redes   y defensa ").category, "REDES Y DEFENSA")

    def test_existing_accented_category_is_preserved(self):
        self.assertEqual(challenge_with_category("CRIPTOGRAFÍA").category, "CRIPTOGRAFÍA")

    def test_rejects_invalid_or_oversized_names(self):
        for name in ("X", " " * 4, "WEB<script>", "A" * 49, "A\nB"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                challenge_with_category(name)


if __name__ == "__main__":
    unittest.main()
