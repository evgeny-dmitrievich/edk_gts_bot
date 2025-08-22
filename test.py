        for j, (file_type, file_id, caption, msg_item, is_document) in enumerate(chunk):
            # Определяем подпись
            if caption and caption.strip():
                cap = make_caption(msg_item.from_user, caption)  # подпись пользователя всегда
            else:
                # дефолтная подпись
                if not is_document and j == 0:
                    cap = make_caption(msg_item.from_user)  # первый фото/видео
                elif is_document and j == len(chunk) - 1:
                    cap = make_caption(msg_item.from_user)  # последний документ
                else:
                    cap = None
