"""Pronunciacion de siglas y palabras tecnicas para Yo, que lee en ingles en voz alta:
"RBAC" -> "RBAC (ár-bak)". Escrita como la leeria alguien que habla espanol; la tilde
marca el acento. Cada vez que aparece, pero solo en lo que se dice
(nunca dentro del codigo de la pizarra).
"""

from __future__ import annotations

import re
from typing import Callable

PRONUNCIATION: dict[str, str] = {
    # siglas
    "RBAC": "ár-bak", "SBOM": "és-bom", "CVE": "si-vi-í", "CVSS": "si-vi-es-és", "eBPF": "i-bi-pi-éf",
    "LSM": "el-es-ém", "IoC": "ái-ou-sí", "MISP": "misp", "SIEM": "sim", "SOC": "sok", "EDR": "i-di-ár",
    "MFA": "em-ef-éi", "SSO": "es-es-óu", "OAuth": "óu-oz", "SAML": "sá-mel", "LDAP": "él-dap",
    "TLS": "ti-el-és", "PKI": "pi-kei-ái", "SCC": "es-si-sí", "IAM": "ái-am", "CDK": "si-di-kéi",
    "YAML": "iá-mel", "JSON": "yéi-son", "sshd": "es-es-eich-dí", "uid": "iu-ai-dí", "euid": "i-iu-ai-dí",
    "ppid": "pi-pid", "tty": "ti-ti-uái", "X.509": "eks-fáiv-ou-náin", "HTCondor": "eich-ti-kón-dor",
    # herramientas y productos
    "Zeek": "zíik, con z zumbada", "Kubernetes": "kiu-ber-né-tis", "kubectl": "kiúb-kon-trol", "OpenShift": "óu-pen-shift",
    "Puppet": "pá-pet", "Ansible": "án-si-bol", "Chef": "shef", "noop": "nóu-op", "sudo": "sú-du",
    "sudoers": "sú-du-ers", "sysctl": "sís-kon-trol", "auditd": "ó-dit-di", "Falco": "fál-kou",
    "Tetragon": "té-tra-gon", "NetScaler": "nét-skei-ler", "Splunk": "splank", "Grafana": "gra-fá-na",
    "Thanos": "zá-nos", "OpenSearch": "óu-pen-serch", "Kafka": "káf-ka", "Keycloak": "kíi-klouk",
    "Barad-Dûr": "bá-rad dur", "Barad-Dur": "bá-rad dur",
    "Azure": "á-shur", "Entra": "én-tra", "Kerberos": "kér-be-ros",
    # comandos de Linux (las opciones con guion se deletrean aparte, ver _FLAG)
    "ls": "el-és", "ps": "pi-és", "ss": "es-és", "aux": "éi-iu-éks", "auxf": "éi-iu-eks-éf",
    "journalctl": "yér-nal-kon-trol", "systemctl": "sís-tem-kon-trol", "systemd": "sís-tem-dí",
    "setuid": "set-iu-ai-dí", "setgid": "set-yi-ai-dí", "crontab": "krón-tab", "netstat": "nét-stat",
    "lsof": "el-es-óf", "chmod": "chi-mód", "chown": "chi-óun", "getcap": "guét-kap",
    "awk": "ok", "strace": "és-treis", "auditctl": "ó-dit-kon-trol", "ausearch": "ó-ser-ch",
    # palabras dificiles
    "Liviu": "lí-vi-u", "SRE": "es-ar-í", "mitigate": "mí-ti-gueit", "mitigation": "mi-ti-guéi-shon",
    "rebuild": "ri-bíld", "beacon": "bí-kon", "beaconing": "bí-ko-ning", "logs": "logs, con g",
    "IMDSv2": "ái-em-di-es vi tu", "WAF": "uáf", "Volatility": "vo-la-tí-li-ti", 
    "lag": "lág, con g", "queued": "kiúd", "replay": "ri-pléi", "backfill": "bák-fil", "exe": "ék-si",
    "principal": "prín-si-pal", "Key Vault": "kíi volt", "augenrules": "ó-guen-rúls", "ruser": "ár-iu-ser",
    "euser": "í-iu-ser", "OpenVox": "óu-pen-voks", "SCuBA": "skú-ba", "idempotency": "ai-dem-póu-ten-si",
    "MailItemsAccessed": "méil-ái-tems-ák-se-st", "sha256sum": "sha-tu-fíf-ti-siks-sam",
    "privilege": "prí-vi-lich", "ransomware": "rán-som-uer", "phishing": "fí-shing", "allowlist": "a-láu-list",
    "namespace": "néim-speis", "vulnerability": "vol-ne-ra-bí-li-ti", "vulnerabilities": "vol-ne-ra-bí-li-tis",
}

_TERMS = re.compile(
    r"(?<![\w.-])(" + "|".join(re.escape(k) for k in sorted(PRONUNCIATION, key=len, reverse=True)) + r")(s?)(?![\w-])",
    re.I)
_KEYS = {k.lower(): k for k in PRONUNCIATION}

# opciones de comando: "-la" -> "dash el-éi", "--no-headers" -> "dash dash no headers"
_FLAG = re.compile(r"(?<!\S)(--?)([A-Za-z][A-Za-z-]*)(?![\w-])")
_LETTERS = dict(zip("abcdefghijklmnopqrstuvwxyz",
                    "éi bi si di i ef yi eich ai yei kei el em en ou pi kiu ar es ti iu vi dábel-iu eks uái sii".split()))


def _flag_hint(dashes: str, name: str) -> str | None:
    if dashes == "--":
        return "dash dash " + name.replace("-", " ")
    if len(name) > 4 or "-" in name:
        return None
    if len(name) > 2 and re.search(r"[aeiou]", name, re.I):
        return "dash " + name  # -perm, -name: se dice como palabra
    spelled = "-".join(_LETTERS[c.lower()] for c in name)
    return "dash " + spelled


def pronounce(text: str, fmt: Callable[[str], str] = lambda hint: f" ({hint})") -> str:
    """Anade la pronunciacion tras cada aparicion de cada termino; `fmt` decide como se ve."""
    text = _TERMS.sub(lambda m: m.group(0) + fmt(PRONUNCIATION[_KEYS[m.group(1).lower()]]), text)

    def flag(m: re.Match) -> str:
        hint = _flag_hint(m.group(1), m.group(2))
        return m.group(0) + fmt(hint) if hint else m.group(0)

    return _FLAG.sub(flag, text)
