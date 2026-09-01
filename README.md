# MiBici Monitor

Recolector histórico de los feeds públicos GBFS 3.0 de MiBici Guadalajara.
Guarda observaciones en archivos JSONL, comprime las horas concluidas con gzip
y las sube a Google Cloud Storage sin sobrescribir objetos existentes.

## Frecuencia

- `station_status`: cada 15 segundos entre 04:45 y 01:15, hora de Guadalajara.
- `station_status`: cada 5 minutos entre 01:15 y 04:45.
- Feeds de metadatos: cada hora.
- Descubrimiento y versiones GBFS: una vez al día.

## Formato en Cloud Storage

```text
gbfs/{feed}/year=YYYY/month=MM/day=DD/hour=HH/YYYY-MM-DDTHH.jsonl.gz
```

Cada línea contiene `observed_at`, `feed`, `source_url`, `sha256` y `payload`.
Las horas y rutas de almacenamiento usan UTC.

## Instalación en Ubuntu

```bash
sudo useradd --system --home /var/lib/mibici-collector --create-home mibici
sudo mkdir -p /opt/mibici-monitor
sudo chown -R mibici:mibici /opt/mibici-monitor /var/lib/mibici-collector
sudo -u mibici python3 -m venv /opt/mibici-monitor/.venv
sudo -u mibici /opt/mibici-monitor/.venv/bin/pip install -r requirements.txt
sudo cp mibici-collector.service /etc/systemd/system/
sudo cp .env.example /etc/mibici-collector.env
sudo chmod 600 /etc/mibici-collector.env
sudo systemctl daemon-reload
sudo systemctl enable --now mibici-collector
```

Edita `/etc/mibici-collector.env` y sustituye `your-bucket-name`. En Compute
Engine se recomienda usar una cuenta de servicio con `roles/storage.objectCreator`
sobre el bucket, sin descargar claves JSON a la VM.

## Verificación

```bash
systemctl status mibici-collector
journalctl -u mibici-collector -f
gcloud storage ls --recursive gs://TU_BUCKET/gbfs/
```

El archivo de la hora actual se conserva localmente. Su subida ocurre después
del cambio de hora UTC.

## Fuentes GBFS

- `station_status`
- `station_information`
- `system_information`
- `system_pricing_plans`
- `system_regions`
- `vehicle_types`
- `geofencing_zones`
- `gbfs`
- `gbfs_versions`

Este proyecto no está afiliado con MiBici. Consume únicamente feeds públicos;
respeta sus términos, disponibilidad y límites operativos.
