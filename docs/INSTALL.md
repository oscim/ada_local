# ============================================================
#  Installation frp pour Ada — Guide complet
# ============================================================

## 1. Télécharger frp (sur le VPS ET sur la machine Ada)

```bash
# Récupérer la dernière version (adapter le numéro de version)
FRP_VERSION="0.61.1"
ARCH="linux_amd64"   # ou linux_arm64 si Raspberry Pi / ARM

wget https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_${ARCH}.tar.gz
tar -xzf frp_${FRP_VERSION}_${ARCH}.tar.gz
cd frp_${FRP_VERSION}_${ARCH}
```


## 2. Sur le VPS — Installer le serveur (frps)

```bash
# Copier le binaire
sudo cp frps /usr/local/bin/
sudo chmod +x /usr/local/bin/frps

# Créer le dossier de config
sudo mkdir -p /etc/frp
sudo cp frps.toml /etc/frp/

# Créer le service systemd
sudo tee /etc/systemd/system/frps.service > /dev/null <<EOF
[Unit]
Description=frp Server (Ada tunnel)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.toml
Restart=always
RestartSec=5
User=nobody

[Install]
WantedBy=multi-user.target
EOF

# Activer et démarrer
sudo systemctl daemon-reload
sudo systemctl enable frps
sudo systemctl start frps

# Vérifier
sudo systemctl status frps
```

### Ouvrir les ports nécessaires sur le VPS

```bash
# Port frp (communication client-serveur)
sudo ufw allow 7000/tcp

# Port exposé pour Ada
sudo ufw allow 6000/tcp

# Dashboard (optionnel, restreindre à ton IP si possible)
sudo ufw allow 7500/tcp
```


## 3. Sur la machine Ada — Installer le client (frpc)

```bash
# Copier le binaire
sudo cp frpc /usr/local/bin/
sudo chmod +x /usr/local/bin/frpc

# Créer le dossier de config
sudo mkdir -p /etc/frp
sudo cp frpc.toml /etc/frp/

# Créer le service systemd
sudo tee /etc/systemd/system/frpc.service > /dev/null <<EOF
[Unit]
Description=frp Client (Ada tunnel vers VPS)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/frpc -c /etc/frp/frpc.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Activer et démarrer
sudo systemctl daemon-reload
sudo systemctl enable frpc
sudo systemctl start frpc

# Vérifier
sudo systemctl status frpc
```


## 4. Tester

Depuis n'importe quel navigateur extérieur :
```
http://TON_VPS_IP:6000
```
→ Tu arrives sur l'interface Ada chez toi.

Dashboard frp (pour voir l'état du tunnel) :
```
http://TON_VPS_IP:7500
```


## 5. Aller plus loin (optionnel)

### Ajouter HTTPS avec un reverse proxy nginx sur le VPS

```nginx
server {
    listen 443 ssl;
    server_name ada.tondomaine.com;

    ssl_certificate     /etc/letsencrypt/live/ada.tondomaine.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ada.tondomaine.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:6000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Ainsi `https://ada.tondomaine.com` → Ada chez toi, avec HTTPS propre.
