class ConsoleWhatsAppBackend:
    """Default backend: logs what would be sent instead of actually sending
    it -- same pattern as Django's console EMAIL_BACKEND. No real WhatsApp
    Business API account/credentials exist yet; swap settings.WHATSAPP_BACKEND
    to a real provider (Twilio, Meta Cloud API, ...) once you have one --
    call sites in services.py don't change.
    """

    def send(self, to_phone, message):
        print(f"[WhatsApp -> {to_phone}]\n{message}\n")
        return True
