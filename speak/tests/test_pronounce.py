import unittest

from speak.notes.pronounce import pronounce


class PronounceTests(unittest.TestCase):
    def test_every_time(self):
        self.assertEqual(pronounce("I would use RBAC and an SBOM, and RBAC again."),
                         "I would use RBAC (ár-bak) and an SBOM (és-bom), and RBAC (ár-bak) again.")

    def test_plurals_and_case(self):
        self.assertEqual(pronounce("New CVEs every day"), "New CVEs (si-vi-í) every day")
        self.assertEqual(pronounce("piping kubectl into grep"), "piping kubectl (kiúb-kon-trol) into grep")

    def test_command_flags(self):
        self.assertEqual(pronounce("run ps auxf and ls -la"),
                         "run ps (pi-és) auxf (éi-iu-eks-éf) and ls (el-és) -la (dash el-éi)")
        self.assertEqual(pronounce("pods -A --no-headers"), "pods -A (dash éi) --no-headers (dash dash no headers)")
        self.assertEqual(pronounce("find / -perm"), "find / -perm (dash perm)")
        self.assertEqual(pronounce("a well-known e-mail - and a re-run"), "a well-known e-mail - and a re-run")

    def test_not_inside_other_words(self):
        self.assertEqual(pronounce("my-sudo-file and pseudo"), "my-sudo-file and pseudo")

    def test_board_and_answer_formats(self):
        from speak.notes.editor import editor_html
        from speak.ui.notes_window import _answer_block

        self.assertIn("RBAC *(ár-bak)*", _answer_block("AL VUELO", "", "I would use RBAC per namespace.", "x"))
        board = "## Plan\n» I would check RBAC first.\nrbac = load()\n» RBAC again."
        out = editor_html(board)
        self.assertEqual(out.count("ár-bak"), 2)  # en cada frase roja, nunca en el codigo
        self.assertIn("rbac = load()", out)  # el codigo no se toca


if __name__ == "__main__":
    unittest.main()
