import asyncio
import time
import urllib.parse

import flet as ft
import httpx

SOURCE_URL = "https://raw.githubusercontent.com/SoliSpirit/mtproto/refs/heads/master/all_proxies.txt"
TIMEOUT = 3.0


class ProxyChecker:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "MTProto Proxy Checker"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 20

        self.working_proxies = []
        self.is_checking = False

        self.total_val = ft.Text("0", size=28, weight=ft.FontWeight.BOLD)
        self.working_val = ft.Text("0", size=28, weight=ft.FontWeight.BOLD)
        self.dead_val = ft.Text("0", size=28, weight=ft.FontWeight.BOLD)

        self.status_text = ft.Text(
            "Нажмите кнопку для проверки прокси",
            size=16,
            color=ft.Colors.GREY_400,
            text_align=ft.TextAlign.CENTER,
        )

        self.progress_bar = ft.ProgressBar(value=0, color=ft.Colors.BLUE_400)
        self.results_list = ft.ListView(expand=True, spacing=8, padding=10)

        self.check_btn = ft.Button(
            content="Проверить прокси",
            icon=ft.Icons.SEARCH,
            on_click=self.start_check,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
        )

        self.clear_btn = ft.Button(
            content="Очистить",
            icon=ft.Icons.DELETE,
            on_click=self.clear_results,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
        )

        self.concurrency_label = ft.Text(
            "Параллельных проверок: 20",
            size=14,
            color=ft.Colors.GREY_400,
        )

        self.slider = ft.Slider(
            min=1, max=100,
            value=20,
            divisions=100,
            label="{value}",
            on_change=self.on_slider_change
        )

        root = ft.Column(
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=15,
            controls=[
                ft.Text("MTProto Proxy Checker", size=24, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Проверка выполняется с вашего устройства",
                    size=12,
                    color=ft.Colors.GREY_500,
                ),
                self.status_text,
                self.progress_bar,
                ft.Row(
                    [
                        self._stat_card("Всего", self.total_val),
                        self._stat_card("Рабочих", self.working_val),
                        self._stat_card("Мёртвых", self.dead_val),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                ),
                self.results_list,
                self.concurrency_label,
                self.slider,
                ft.Row(
                    [self.check_btn, self.clear_btn],
                    alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                    spacing=10,
                ),
            ],
        )

        self.page.add(root)

    def _stat_card(self, label, value_text):
        return ft.Container(
            content=ft.Column(
                controls=[
                    value_text,
                    ft.Text(label, size=12, color=ft.Colors.GREY_500),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=2,
            ),
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
            padding=15,
            border_radius=10,
            expand=True,
        )

    async def check_proxy(self, server, port, url, semaphore):
        async with semaphore:
            try:
                start = time.perf_counter()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(server, port), timeout=TIMEOUT
                )
                ping = round((time.perf_counter() - start) * 1000, 1)
                writer.close()
                await writer.wait_closed()
                return (url, ping)
            except Exception:
                return None

    async def start_check(self, e):
        if self.is_checking:
            return
        self.is_checking = True
        self.check_btn.disabled = True
        self.check_btn.content = "Проверяем..."
        self.status_text.value = "Загрузка списка..."
        self.results_list.controls = []
        self.progress_bar.value = 0
        self.page.update()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(SOURCE_URL)
                response.raise_for_status()
                lines = response.text.splitlines()

            tasks = []
            for line in lines:
                line = line.strip()
                if line.startswith("https://t.me/proxy"):
                    parsed = urllib.parse.urlparse(line)
                    params = urllib.parse.parse_qs(parsed.query)
                    server = params.get("server", [""])[0].strip().rstrip(".")
                    port_str = params.get("port", [""])[0]
                    if server and port_str:
                        tasks.append((server, int(port_str), line))

            total = len(tasks)
            self.total_val.value = str(total)
            self.status_text.value = f"Проверяем {total} прокси..."
            self.page.update()

            value = self.slider.value
            concurrency = int(value) if value is not None else 25
            semaphore = asyncio.Semaphore(concurrency)
            completed = 0

            async def check_and_track(server, port, url):
                nonlocal completed
                result = await self.check_proxy(server, port, url, semaphore)
                completed += 1
                self.progress_bar.value = completed / total
                if completed % 15 == 0 or completed == total:
                    self.status_text.value = f"Проверено {completed}/{total}"
                    self.page.update()
                return result

            results = await asyncio.gather(
                *[check_and_track(s, p, u) for s, p, u in tasks]
            )

            self.working_proxies = [r for r in results if r is not None]
            self.working_proxies.sort(key=lambda x: x[1])

            working_count = len(self.working_proxies)
            self.working_val.value = str(working_count)
            self.dead_val.value = str(total - working_count)
            self.status_text.value = f"Готово! Найдено {working_count} рабочих прокси"
            self.progress_bar.value = 1.0

            cards = []
            for url, ping in self.working_proxies:
                tg_link = url.replace("https://t.me/", "tg://")
                if ping < 150:
                    ping_color = ft.Colors.GREEN_400
                elif ping < 300:
                    ping_color = ft.Colors.ORANGE_400
                else:
                    ping_color = ft.Colors.RED_400

                cards.append(
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Button(
                                    content="Применить",
                                    expand=True,
                                    action=ft.OpenUrl(url=tg_link, target=ft.UrlTarget.BLANK),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.CONTENT_COPY,
                                    data=tg_link,
                                    icon_color=ft.Colors.BLUE_300,
                                    tooltip="Скопировать",
                                    on_click=self.copy_to_clipboard,
                                ),
                                ft.Container(
                                    content=ft.Text(
                                        f"{ping} мс",
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color=ft.Colors.WHITE,
                                    ),
                                    bgcolor=ping_color,
                                    padding=ft.Padding.symmetric(vertical=6, horizontal=10),
                                    border_radius=12,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=8,
                        ),
                        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                        padding=12,
                        border_radius=8,
                    )
                )
            self.results_list.controls = cards
            self.page.update()

        except Exception as ex:
            self.status_text.value = f"Ошибка: {str(ex)}"
            self.page.update()
        finally:
            self.is_checking = False
            self.check_btn.disabled = False
            self.check_btn.content = "Проверить прокси"
            self.page.update()

    def on_slider_change(self, e):
        value = self.slider.value
        concurrency = int(value) if value is not None else 25
        self.concurrency_label.value = f"Параллельных проверок: {concurrency}"
        self.page.update()

    async def copy_to_clipboard(self, e):
        link = e.control.data
        try:
            await ft.Clipboard().set(link)
            self.page.show_dialog(
                ft.SnackBar(ft.Text("Ссылка скопирована в буфер обмена"))
            )
        except Exception as ex:
            self.page.show_dialog(ft.SnackBar(ft.Text(f"Ошибка копирования: {ex}")))

    async def clear_results(self, e):
        if self.is_checking:
            return
        self.working_proxies = []
        self.results_list.controls = []
        self.status_text.value = "Нажмите кнопку для проверки прокси"
        self.progress_bar.value = 0
        self.total_val.value = "0"
        self.working_val.value = "0"
        self.dead_val.value = "0"
        self.page.update()


def main(page: ft.Page):
    page.window.icon = "icon.png"
    ProxyChecker(page)


if __name__ == "__main__":
    ft.run(main)
