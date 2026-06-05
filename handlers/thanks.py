def register(app):
    @app.command("/thanks")
    def handle_thanks(ack, body, client):
        ack()
        client.chat_postEphemeral(
            channel=body["channel_id"],
            user=body["user_id"],
            text="🚧 준비 중입니다."
        )
