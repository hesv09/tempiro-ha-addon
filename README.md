# Tempiro Energy Monitor - Home Assistant Add-on

Monitor and analyze energy consumption from Tempiro smart breakers with spot price integration.

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fhesv09%2Ftempiro-ha-addon)

## Features

- **Energy Monitoring**: Track energy consumption from Tempiro smart breakers
- **Spot Price Integration**: Automatic electricity prices from elprisetjustnu.se (SE3)
- **Cost Calculation**: Real-time cost calculation based on actual spot prices
- **Historical Data**: SQLite database for historical analysis
- **Beautiful Dashboard**: Built-in responsive dashboard optimized for Home Assistant
- **Auto Sync**: Background sync every hour

## Installation

### Method 1: Add Repository (Recommended)

1. Click the button above, or:
2. Go to **Settings** → **Add-ons** → **Add-on Store**
3. Click the menu (⋮) → **Repositories**
4. Add: `https://github.com/hesv09/tempiro-ha-addon`
5. Find "Tempiro Energy Monitor" and click **Install**

### Method 2: Manual Installation

1. Copy the `tempiro` folder to `/addons/` on your Home Assistant
2. Go to **Settings** → **Add-ons** → **Add-on Store**
3. Click the menu (⋮) → **Check for updates**
4. Find "Tempiro Energy Monitor" and click **Install**

## Configuration

After installation, configure the add-on:

```yaml
tempiro_username: your-email@example.com
tempiro_password: your-password
price_area: SE3
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `tempiro_username` | Your Tempiro account email | Required |
| `tempiro_password` | Your Tempiro account password | Required |
| `price_area` | Electricity price area (SE1-SE4) | SE3 |

## Usage

### Access the Dashboard

After starting the add-on, access the dashboard at:
- **Sidebar**: Click "Tempiro Energy" in the HA sidebar
- **Direct URL**: `http://homeassistant.local:5001/ha`

### Add to Lovelace Dashboard

Add an iframe card to your dashboard:

```yaml
type: iframe
url: /api/hassio_ingress/YOUR_ADDON_SLUG/ha
aspect_ratio: 100%
```

Or use the full URL:

```yaml
type: iframe
url: http://homeassistant.local:5001/ha
aspect_ratio: 100%
```

## Backfill Historical Data

To fetch historical data, use the built-in backfill feature:

1. Access the add-on's web terminal
2. Run: `python backfill.py --days 90`

Or use the API endpoint:
```bash
curl -X POST http://homeassistant.local:5001/api/sync
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /ha` | Simplified dashboard for HA |
| `GET /analysis` | Full analysis dashboard |
| `GET /api/analytics/daily` | Daily energy/cost data |
| `POST /api/sync` | Trigger manual sync |
| `GET /api/sync/status` | Check sync status |

## Screenshots

![Dashboard](https://github.com/hesv09/tempiro-ha-addon/raw/main/images/dashboard.png)

## Support

- [GitHub Issues](https://github.com/hesv09/tempiro-ha-addon/issues)
- [Home Assistant Community](https://community.home-assistant.io/)

## License

MIT License - See LICENSE file for details.

## Credits

- Tempiro API integration
- Spot prices from [elprisetjustnu.se](https://www.elprisetjustnu.se/)
- Built with Flask and Chart.js
