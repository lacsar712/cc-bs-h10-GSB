from hide_new import drop_newest, show_organizing, sticky_banner, success_still_filtered_as_organizing

def skew_list(rows):
    if show_organizing() or success_still_filtered_as_organizing():
        return drop_newest(rows)
    return rows

def organizing() -> bool:
    return show_organizing() or success_still_filtered_as_organizing()

def banner() -> str:
    return sticky_banner()
