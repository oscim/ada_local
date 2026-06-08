#!/usr/bin/env python3
"""
ADA Web Plugin — Lanceur standalone

Usage :
    python3 web_server.py              # HTTPS auto-signé, port 7654
    python3 web_server.py --port 8080
    python3 web_server.py --no-ssl     # HTTP uniquement (micro désactivé sur mobile)

Ne modifie aucun fichier existant du projet.
"""
import argparse
import datetime
import ipaddress
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Supprimer les InsecureRequestWarning urllib3 (services internes avec certs auto-signés)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import uvicorn


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


def _local_ips() -> list[str]:
    """Retourne toutes les IPv4 locales de la machine."""
    ips: set[str] = {"127.0.0.1"}
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            addr = info[4][0]
            if ":" not in addr:
                ips.add(addr)
    except Exception:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
    except Exception:
        pass
    return list(ips)


def _generate_cert(cert_path: Path, key_path: Path) -> bool:
    """Génère un certificat SSL auto-signé valable 10 ans."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        san: list = [
            x509.DNSName("localhost"),
            x509.DNSName(socket.gethostname()),
        ]
        for ip in _local_ips():
            try:
                san.append(x509.IPAddress(ipaddress.ip_address(ip)))
            except ValueError:
                pass

        subject = issuer = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "ADA Local")]
        )
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .sign(key, hashes.SHA256())
        )

        cert_path.parent.mkdir(parents=True, exist_ok=True)
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        return True
    except Exception as exc:
        print(f"  ⚠  Génération SSL échouée : {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(description="ADA Mobile Web Server")
    parser.add_argument("--host", default=os.getenv("ADA_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=_env_int("ADA_WEB_PORT", 7654))
    parser.add_argument(
        "--no-ssl",
        action="store_true",
        default=not _env_bool("ADA_WEB_SSL", True),
        help="Forcer HTTP — le micro ne fonctionnera PAS sur mobile",
    )
    parser.add_argument("--reload", action="store_true", help="Dev: rechargement auto")
    parser.add_argument(
        "--http-callback-port", type=int, default=_env_int("ADA_HTTP_CALLBACK_PORT", 7655),
        help="Port HTTP interne pour les callbacks services (n8n, HA…). 0 = désactivé.",
    )
    args = parser.parse_args()

    root = Path(__file__).parent
    certs_dir = Path(os.getenv("ADA_CERTS_DIR", str(root / "web" / "certs")))
    if not certs_dir.is_absolute():
        certs_dir = root / certs_dir
    cert_path = certs_dir / "cert.pem"
    key_path = certs_dir / "key.pem"

    use_ssl = not args.no_ssl
    if use_ssl:
        if not (cert_path.exists() and key_path.exists()):
            print("  Génération du certificat SSL auto-signé (10 ans)…")
            use_ssl = _generate_cert(cert_path, key_path)
            if use_ssl:
                print("  Certificat créé dans web/certs/\n")

    proto = "https" if use_ssl else "http"
    ips = _local_ips()

    print(f"\n  ADA Mobile Web Server  {'[HTTPS]' if use_ssl else '[HTTP]'}")
    print(f"  ──────────────────────────────────────")
    for ip in sorted(ips):
        if ip != "127.0.0.1":
            print(f"  Réseau : {proto}://{ip}:{args.port}")
    print(f"  Local  : {proto}://localhost:{args.port}")

    cb_port = args.http_callback_port
    if use_ssl and cb_port:
        for ip in sorted(ips):
            if ip != "127.0.0.1":
                print(f"  Callbacks n8n/HA : http://{ip}:{cb_port}  (HTTP, pas de cert requis)")

    if use_ssl:
        print()
        print("  ⚠  Première visite — accepter le certificat auto-signé :")
        print("     Android Chrome : 'Paramètres avancés' → 'Continuer'")
        print("     iOS Safari     : 'Afficher le certificat' → 'Se fier'")
    print()

    run_kwargs: dict = dict(
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    if use_ssl:
        run_kwargs["ssl_certfile"] = str(cert_path)
        run_kwargs["ssl_keyfile"] = str(key_path)

    # Démarrer le listener HTTP interne (callbacks n8n / HA) si HTTPS actif
    if use_ssl and cb_port:
        import threading
        def _run_http_callback():
            import uvicorn as _uv
            _uv.run(
                "web.server:app",
                host=args.host,
                port=cb_port,
                log_level="warning",
            )
        _t = threading.Thread(target=_run_http_callback, daemon=True, name="ada-http-callback")
        _t.start()

    uvicorn.run("web.server:app", **run_kwargs)


if __name__ == "__main__":
    main()
