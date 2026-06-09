"""Обратные и прямые связи между объектами метаданных."""

from __future__ import annotations

from typing import Any

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.kb_index import load_kb_index
from packages.kb.indexer.references import find_references
from packages.kb.indexer.store import get_by_metadata


def list_by_relation(
    config: ProfileConfig,
    relation: str,
    *,
    object_type: str = "",
    object_name: str = "",
    limit: int = 50,
) -> str:
    relation = (relation or "").lower()
    index = load_kb_index(config)

    if relation == "documents_by_register":
        if not object_name:
            return "Укажите object_name — имя регистра."
        reg_key = f"{object_type or 'AccumulationRegister'}:{object_name}"
        docs = (index.get("register_to_documents") or {}).get(reg_key, [])
        if not docs:
            return f"Документы, двигающие {reg_key}, не найдены."
        lines = [f"## Документы по регистру {reg_key}\n"]
        for item in docs[:limit]:
            kind = f" ({item['movement_kind']})" if item.get("movement_kind") else ""
            lines.append(f"- {item.get('document_type', 'Document')}.{item['document']}{kind}")
        return "\n".join(lines)

    if relation == "registers_by_document":
        if not object_type or not object_name:
            return "Укажите object_type и object_name документа."
        obj = (index.get("objects") or {}).get(f"{object_type}:{object_name}")
        if not obj:
            return f"Объект {object_type}.{object_name} не найден в KB-индексе."
        movements = obj.get("movements") or []
        if not movements:
            return f"У {object_type}.{object_name} нет движений по регистрам."
        lines = [f"## Регистры документа {object_type}.{object_name}\n"]
        for mov in movements[:limit]:
            kind = f" — {mov['movement_kind']}" if mov.get("movement_kind") else ""
            lines.append(f"- {mov.get('register_type')}.{mov.get('register_name')}{kind}")
        return "\n".join(lines)

    if relation == "references_to_object":
        if not object_name:
            return "Укажите object_name."
        identifier = object_name
        refs = find_references(config, identifier, limit=limit, object_type=object_type)
        if not refs:
            return f"Ссылки на «{identifier}» не найдены."
        lines = [f"## Ссылки на {object_type + '.' if object_type else ''}{identifier}\n"]
        for r in refs[:limit]:
            lines.append(f"- {r['relative_path']}:{r['line']} — `{r['context'][:120]}`")
        return "\n".join(lines)

    if relation == "objects_in_subsystem":
        if not object_name:
            return "Укажите object_name — имя подсистемы."
        items = (index.get("subsystem_objects") or {}).get(object_name)
        if items:
            lines = [f"## Объекты подсистемы «{object_name}»\n"]
            lines.extend(f"- {item}" for item in items[:limit])
            if len(items) > limit:
                lines.append(f"\n... и ещё {len(items) - limit}")
            return "\n".join(lines)

        where: dict[str, Any] = {
            "$and": [
                {"kind": "metadata"},
            ]
        }
        all_data = get_by_metadata(config, where=where)
        metas = all_data.get("metadatas", [])
        matched = []
        for meta in metas:
            subs = str(meta.get("subsystems", "")).split(",")
            if object_name in [s.strip() for s in subs if s.strip()]:
                matched.append(f"{meta.get('object_type')}.{meta.get('object_name')}")
        if not matched:
            return f"Подсистема «{object_name}» не найдена или пуста."
        lines = [f"## Объекты подсистемы «{object_name}»\n"]
        lines.extend(f"- {item}" for item in sorted(matched)[:limit])
        lines.append(f"\nВсего: {len(matched)}")
        return "\n".join(lines)

    return (
        f"Неизвестная связь relation={relation!r}. "
        "Допустимо: documents_by_register, registers_by_document, "
        "references_to_object, objects_in_subsystem."
    )
