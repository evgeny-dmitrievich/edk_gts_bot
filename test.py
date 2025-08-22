for j, (file_type, file_id, caption, msg_item, is_document) in enumerate(chunk):
    if caption:
        # Пользователь написал подпись — используем для этого файла
        cap = make_caption(msg_item.from_user, caption)
    else:
        # Пользователь не писал подпись
        if file_type in ("photo", "video"):
            cap = make_caption(msg_item.from_user) if j == 0 else None
        elif is_document:
            cap = make_caption(msg_item.from_user) if j == len(chunk) - 1 else None
        else:
            cap = None
