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
    "Zeek": "siik", "Kubernetes": "kiu-ber-né-tis", "kubectl": "kiúb-kon-trol", "OpenShift": "óu-pen-shift",
    "Puppet": "pá-pet", "Ansible": "án-si-bol", "Chef": "shef", "noop": "nóu-op", "sudo": "sú-du",
    "sudoers": "sú-du-ers", "sysctl": "sís-kon-trol", "auditd": "ó-dit-di", "Falco": "fál-kou",
    "Tetragon": "té-tra-gon", "NetScaler": "nét-skei-ler", "Splunk": "splank", "Grafana": "gra-fá-na",
    "Thanos": "zá-nos", "OpenSearch": "óu-pen-serch", "Kafka": "káf-ka", "Keycloak": "kíi-klouk",
    "Azure": "á-shur", "Entra": "én-tra", "Kerberos": "kér-be-ros",
    # palabras dificiles
    "privilege": "prí-vi-lich", "ransomware": "rán-som-uer", "phishing": "fí-shing", "allowlist": "a-láu-list",
    "namespace": "néim-speis", "vulnerability": "vol-ne-ra-bí-li-ti", "vulnerabilities": "vol-ne-ra-bí-li-tis",
}

_TERMS = re.compile(
    r"(?<![\w.-])(" + "|".join(re.escape(k) for k in sorted(PRONUNCIATION, key=len, reverse=True)) + r")(s?)(?![\w-])",
    re.I)
_KEYS = {k.lower(): k for k in PRONUNCIATION}


def pronounce(text: str, fmt: Callable[[str], str] = lambda hint: f" ({hint})") -> str:
    """Anade la pronunciacion tras cada aparicion de cada termino; `fmt` decide como se ve."""
    return _TERMS.sub(lambda m: m.group(0) + fmt(PRONUNCIATION[_KEYS[m.group(1).lower()]]), text)
