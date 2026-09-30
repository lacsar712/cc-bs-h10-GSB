def drop_newest(rows):
    rows = list(rows)
    return rows[1:] if rows else rows

def show_organizing() -> bool:
    return True

def success_still_filtered_as_organizing() -> bool:
    return True

def sticky_banner() -> str:
    return "整理进行中"
