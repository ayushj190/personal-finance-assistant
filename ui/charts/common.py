from ui.theme import hex_to_rgba

# Aligned Investment Asset Class and Sector Color Maps
ASSET_TYPE_COLORS = {
    "STOCK": "#38BDF8",
    "ETF": "#2DD4BF",
    "CRYPTO": "#34D399",
    "COMMODITY": "#FBBF24",
    "BOND": "#A78BFA",
    "CASH": "#94A3B8",
    "OTHER": "#CBD5E1",
}

SECTOR_COLORS = {
    "Technology": "#38BDF8",
    "Broad Market ETF": "#2DD4BF",
    "Financial Services": "#818CF8",
    "Energy": "#FB7185",
    "Consumer & Entertainment": "#F472B6",
    "Healthcare": "#10B981",
    "Industrials & Materials": "#FB923C",
    "Real Estate": "#FBBF24",
    "Cryptocurrency": "#34D399",
    "Gold & Metals": "#F59E0B",
    "Bonds & Fixed Income": "#A78BFA",
    "Defense & Aerospace": "#C084FC",
    "Other / Diversified": "#64748B",
    "Diversified": "#64748B",
    "Other": "#94A3B8",
}

SECTOR_RGBA_COLORS = {k: hex_to_rgba(v, 0.65) for k, v in SECTOR_COLORS.items()}
