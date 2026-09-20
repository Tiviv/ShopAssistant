import asyncio
from aiosmtpd.controller import Controller


class FileDumpHandler:
    async def handle_DATA(self, server, session, envelope):
        with open("/tmp/smtp_catcher_inbox.txt", "a") as f:
            f.write(envelope.content.decode("utf8", errors="replace"))
            f.write("\n-----END MESSAGE-----\n")
        return "250 Message accepted for delivery"


if __name__ == "__main__":
    open("/tmp/smtp_catcher_inbox.txt", "w").close()
    controller = Controller(FileDumpHandler(), hostname="127.0.0.1", port=10250)
    controller.start()
    print("SMTP catcher listening on 127.0.0.1:10250, dumping to /tmp/smtp_catcher_inbox.txt")
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        controller.stop()
