from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from packages.kb.indexer.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from packages.kb.indexer.chunkers import chunk_bsl, chunk_doc, chunk_metadata, chunk_subsystem
from packages.kb.indexer.config import ProfileConfig, load_config
from packages.kb.indexer.embeddings import embed_texts
from packages.kb.indexer.exceptions import IndexJobCancelledError, IndexerError, SourceNotFoundError
from packages.kb.indexer.extract_bsl import extract_bsl_procedures, extract_module_header
from packages.kb.indexer.extract_docs import extract_doc_sections
from packages.kb.indexer.extract_metadata import extract_metadata
from packages.kb.indexer.extract_subsystems import extract_subsystem
from packages.kb.indexer.incremental import preview_incremental, resolve_incremental_paths
from packages.kb.indexer.index_state import save_manifest_from_scan, update_manifest_after_index
from packages.kb.indexer.models import Chunk, FileKind, SourceFormat
from packages.kb.indexer.profiles import list_profiles
from packages.kb.indexer.keyword_index import build_keyword_index, merge_keyword_index
from packages.kb.indexer.kb_index import build_kb_index
from packages.kb.indexer.metadata_snapshot import build_metadata_snapshot
from packages.kb.indexer.progress import IndexProgress, ProgressCallback
from packages.kb.indexer.reference_index import build_reference_index
from packages.kb.indexer.scanner import scan_profile
from packages.kb.indexer.store import (
    count_chunks,
    delete_by_path,
    path_has_chunks,
    reset_collection_store,
    reset_store_cache,
    upsert_chunks,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _embed_batch(chunks: list[Chunk], config: ProfileConfig) -> list[Chunk]:
    texts = [chunk.text for chunk in chunks]
    embeddings = embed_texts(texts, config.embeddings)
    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding
    return chunks


def _process_file(config: ProfileConfig, entry) -> list[Chunk]:
    chunks: list[Chunk] = []
    if entry.kind == FileKind.METADATA:
        obj = extract_metadata(entry.path, entry.source_name, entry.source_format)
        chunks.extend(chunk_metadata(config, obj))
        if entry.source_format == SourceFormat.EDT and obj.object_type == "Subsystem":
            subsystem = extract_subsystem(entry.path, entry.source_name, entry.source_format)
            if subsystem:
                chunks.extend(chunk_subsystem(config, subsystem))
    elif entry.kind == FileKind.BSL:
        procedures = extract_bsl_procedures(entry.path)
        header = extract_module_header(entry.path)
        chunks.extend(chunk_bsl(config, entry.path, procedures, module_header=header))
    elif entry.kind == FileKind.MARKDOWN:
        for section in extract_doc_sections(entry.path, entry.source_name):
            chunks.append(chunk_doc(config, section))
    return chunks


def _check_cancel(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel and should_cancel():
        raise IndexJobCancelledError("Индексация отменена")


def _checkpoint_confirmed_paths(config: ProfileConfig, paths: list[str]) -> list[str]:
    """Файлы из checkpoint, чанки которых реально есть в Chroma."""
    confirmed: list[str] = []
    for raw in paths:
        norm = str(Path(raw).expanduser().resolve())
        if path_has_chunks(config, norm):
            confirmed.append(norm)
    return confirmed


def _flush_pending_chunks(
    config: ProfileConfig,
    pending: list[Chunk],
    *,
    progress: IndexProgress,
    on_progress: ProgressCallback | None,
    done_paths: list[str],
    full: bool,
) -> int:
    if not pending:
        return 0
    progress.set_phase("embedding")
    if on_progress:
        on_progress(progress)
    batch = _embed_batch(pending, config)
    progress.set_phase("upserting")
    if on_progress:
        on_progress(progress)
    upsert_chunks(config, batch)
    written = len(batch)
    paths_written = {
        str(Path(chunk.metadata.get("path", "")).expanduser().resolve())
        for chunk in batch
        if chunk.metadata.get("path")
    }
    for path in sorted(paths_written):
        if path not in done_paths:
            done_paths.append(path)
    if full and done_paths:
        save_checkpoint(
            config,
            processed_paths=done_paths,
            phase=progress.phase,
            full=True,
        )
    pending.clear()
    return written


def _make_cli_bar(total: int, enabled: bool):
    if not enabled or total <= 0:
        return None
    try:
        from tqdm import tqdm

        return tqdm(total=total, desc="Индексация", unit="файл")
    except ImportError:
        return None


def run_index(
    config: ProfileConfig,
    full: bool = False,
    changed_paths: list[str] | None = None,
    deleted_paths: list[str] | None = None,
    on_progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
    resume: bool = False,
    cli_progress: bool = False,
) -> dict:
    resumed_paths: list[str] = []
    if full and resume:
        checkpoint = load_checkpoint(config)
        if checkpoint and checkpoint.get("full"):
            raw_paths = list(checkpoint.get("processed") or [])
            reset_store_cache()
            resumed_paths = _checkpoint_confirmed_paths(config, raw_paths)
            skipped = len(raw_paths) - len(resumed_paths)
            if skipped:
                logger.warning(
                    "Checkpoint: %d файлов без чанков в Chroma — будут проиндексированы заново",
                    skipped,
                )
            logger.info(
                "Возобновление индексации: пропуск %d файлов с записанными чанками",
                len(resumed_paths),
            )
        else:
            resume = False

    if full and not resume:
        clear_checkpoint(config)
        reset_collection_store(config)
        logger.info("Коллекция '%s' пересоздана", config.store.collection)

    files_deleted = 0
    if deleted_paths:
        for path in deleted_paths:
            files_deleted += delete_by_path(config, path)

    progress = IndexProgress()
    progress.set_phase("scanning")
    if on_progress:
        on_progress(progress)

    try:
        entries = scan_profile(config)
    except SourceNotFoundError:
        raise
    except Exception as exc:
        raise SourceNotFoundError("Ошибка сканирования", details=str(exc)) from exc

    if changed_paths is not None:
        changed_set = {str(Path(p).resolve()) for p in changed_paths}
        entries = [e for e in entries if str(Path(e.path).resolve()) in changed_set]

    all_entries_count = len(entries)
    resumed_set = {str(Path(p).resolve()) for p in resumed_paths}
    if resumed_set:
        entries = [e for e in entries if str(Path(e.path).resolve()) not in resumed_set]

    total_files = all_entries_count
    processed_done = len(resumed_paths)
    total_chunks = 0
    errors = 0
    pending: list[Chunk] = []
    all_chunks: list[Chunk] = []
    mode = "full" if full else ("incremental" if changed_paths is not None else "update")
    progress.total_files = total_files
    progress.set_phase("chunking")

    logger.info(
        "Профиль: %s | формат: %s | проект: %s | режим: %s | файлов: %d",
        config.profile_name,
        config.format,
        config.source_base,
        mode,
        total_files,
    )

    pbar = _make_cli_bar(len(entries), cli_progress)
    done_paths = list(resumed_paths)

    for entry in entries:
        _check_cancel(should_cancel)
        processed_done += 1
        progress.update_file(processed_done, entry.path, total_files)
        if on_progress:
            on_progress(progress)
        if pbar:
            pbar.update(1)
        try:
            if changed_paths is not None:
                delete_by_path(config, entry.path)
            file_chunks = _process_file(config, entry)
            pending.extend(file_chunks)
            all_chunks.extend(file_chunks)
            progress.update_chunks_stats(
                produced=len(all_chunks),
                written=total_chunks,
                files_done=processed_done,
            )
            if len(pending) >= config.embeddings.batch_size:
                total_chunks += _flush_pending_chunks(
                    config,
                    pending,
                    progress=progress,
                    on_progress=on_progress,
                    done_paths=done_paths,
                    full=full,
                )
                progress.update_chunks_stats(
                    produced=len(all_chunks),
                    written=total_chunks,
                    files_done=processed_done,
                )
                if on_progress:
                    on_progress(progress)
                logger.info("Записано чанков: %d", total_chunks)
            elif not file_chunks:
                done_paths.append(str(Path(entry.path).resolve()))
                if full:
                    save_checkpoint(
                        config,
                        processed_paths=done_paths,
                        phase=progress.phase,
                        full=True,
                    )
        except Exception as exc:
            errors += 1
            progress.errors = errors
            logger.error("Ошибка %s: %s", entry.path, exc)

    if pbar:
        pbar.close()

    _check_cancel(should_cancel)
    if pending:
        total_chunks += _flush_pending_chunks(
            config,
            pending,
            progress=progress,
            on_progress=on_progress,
            done_paths=done_paths,
            full=full,
        )
        progress.update_chunks_stats(
            produced=len(all_chunks),
            written=total_chunks,
            files_done=processed_done,
        )

    progress.set_phase("finalizing")
    progress.update_chunks_stats(
        produced=total_chunks,
        written=total_chunks,
        files_done=max(processed_done, 1),
    )
    # force=True: job ещё RUNNING, обычный count_chunks вернёт устаревший progress (0).
    total_in_collection = count_chunks(config, force=True)
    progress.message = f"Готово: {total_files} файлов, {total_chunks} чанков"
    if on_progress:
        on_progress(progress)

    logger.info(
        "Готово [%s]: файлов=%d, чанков=%d, удалено=%d, ошибок=%d, в коллекции=%d",
        config.profile_name,
        total_files,
        total_chunks,
        files_deleted,
        errors,
        total_in_collection,
    )

    if full:
        if errors == 0 and (total_chunks > 0 or total_files == 0):
            clear_checkpoint(config)
            save_manifest_from_scan(config)
        elif errors:
            logger.warning(
                "Checkpoint сохранён: индексация завершилась с %d ошибками",
                errors,
            )
    elif changed_paths is not None:
        update_manifest_after_index(
            config,
            processed_paths=changed_paths,
            deleted_paths=deleted_paths,
        )

    try:
        embedded_chunks = [c for c in all_chunks if c.embedding]
        if embedded_chunks:
            if full:
                build_keyword_index(config, embedded_chunks)
            else:
                merge_keyword_index(config, embedded_chunks, deleted_paths=deleted_paths)
        bsl_entries = [e for e in entries if e.kind == FileKind.BSL]
        if bsl_entries:
            if full:
                build_reference_index(config, bsl_entries)
            else:
                build_reference_index(config, None)
        if full:
            build_metadata_snapshot(config)
            build_kb_index(config)
    except Exception as exc:
        logger.warning("Построение вспомогательных индексов: %s", exc)

    return {
        "mode": mode,
        "resumed_files": len(resumed_paths),
        "files_processed": total_files,
        "chunks_written": total_chunks,
        "files_deleted": files_deleted,
        "errors": errors,
        "chunks_in_collection": total_in_collection,
        "progress": progress.to_dict(),
    }


def run_incremental_index(
    config: ProfileConfig,
    on_progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
    cli_progress: bool = False,
) -> dict:
    modified, deleted, preview = resolve_incremental_paths(config)
    result = run_index(
        config,
        full=False,
        changed_paths=modified,
        deleted_paths=deleted,
        on_progress=on_progress,
        should_cancel=should_cancel,
        cli_progress=cli_progress,
    )
    result["modified_files"] = modified
    result["deleted_files"] = deleted
    result["git_root"] = preview.get("git_root", "")
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Индексация векторной базы знаний 1С")
    parser.add_argument("--profile", "-p", required=True, help="Имя профиля из profiles/")
    parser.add_argument("--full", action="store_true", help="Полная переиндексация")
    parser.add_argument("--incremental", action="store_true", help="Инкремент по изменениям")
    parser.add_argument("--preview-changes", action="store_true", help="Показать изменения без индексации")
    parser.add_argument("--dry-run", action="store_true", help="Только сканирование")
    parser.add_argument("--list", action="store_true", help="Список профилей")
    parser.add_argument("--export", metavar="PATH", help="Экспорт индекса в .tar.gz")
    parser.add_argument("--import", dest="import_path", metavar="PATH", help="Импорт индекса из .tar.gz")
    parser.add_argument("--import-target", metavar="NAME", help="Имя профиля при импорте")
    parser.add_argument("--overwrite", action="store_true", help="Перезаписать профиль при импорте")
    parser.add_argument("--resume", action="store_true", help="Продолжить прерванную полную индексацию")
    parser.add_argument("--progress", action="store_true", help="Прогресс-бар в терминале (tqdm)")
    args = parser.parse_args(argv)

    if args.list:
        for name in list_profiles():
            print(name)
        return

    if args.export:
        from packages.kb.indexer.index_archive import export_index

        path = export_index(args.profile, Path(args.export))
        print(f"Экспорт: {path}")
        return

    if args.import_path:
        from packages.kb.indexer.index_archive import import_index

        name = import_index(
            args.import_path,
            target_profile=args.import_target or args.profile,
            overwrite=args.overwrite,
        )
        print(f"Импортирован профиль: {name}")
        return

    config = load_config(args.profile)

    if args.dry_run:
        try:
            entries = scan_profile(config)
        except IndexerError as exc:
            logger.error("%s", exc)
            sys.exit(1)
        print(f"Профиль: {config.profile_name}")
        print(f"Найдено файлов: {len(entries)}")
        for kind in FileKind:
            count = sum(1 for e in entries if e.kind == kind)
            print(f"  {kind.value}: {count}")
        return

    if args.preview_changes:
        preview = preview_incremental(config)
        print(f"Git: {preview.get('git_root') or '—'}")
        print(f"Изменено: {preview['modified_count']}, удалено: {preview['deleted_count']}")
        for path in preview["modified"]:
            print(f"  M {path}")
        for path in preview["deleted"]:
            print(f"  D {path}")
        return

    try:
        if args.incremental and not args.full:
            run_incremental_index(config, cli_progress=args.progress)
        else:
            run_index(
                config,
                full=args.full or args.resume,
                resume=args.resume,
                cli_progress=args.progress,
            )
    except IndexerError as exc:
        logger.error("%s", exc)
        sys.exit(1)


def main_deprecated() -> None:
    import sys

    print("kb-index устарел; используйте 1c-cursor-kb-index.", file=sys.stderr)
    main()


if __name__ == "__main__":
    main(sys.argv[1:])
