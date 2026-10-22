# Image attachments

Task Sources displays a deduplicated gallery of task sources and stage evidence.
A stage displays its own evidence only. Attaching one path to several stages
does not copy the file. Removing a source reference does not delete the original
or historical evidence. An image still attached to a stage remains in the task
gallery after removing its direct task reference.

Open a gallery image to view it, then use the arrows on its left and right to
move through that gallery in thumbnail order. The previous arrow is disabled
at the first image and the next arrow at the last. Both arrows are disabled
when viewing a single image.

Use the file picker in task/stage editing for multiple local files. Save the
editor to publish the references. Uploading a file alone does not attach it.
New uploads use immutable `hub-artifact/<descriptor hash>/<name>` references
in the existing Hub CAS outside product checkouts. Cancelled drafts can leave
unreferenced versions; no automatic deletion runs because history may need them.
Existing project paths and historical image references continue to resolve.

The picker accepts any file format up to 20 MiB. Unsupported previews retain
metadata and an original download. Image previews are validated separately;
the legacy `/api/v1/images/upload` endpoint still validates image signatures.
`/api/v1/artifacts/upload` stores opaque bytes with optional `roles` and an
explicit registered `previous` reference. Roles describe evidence, deliverables,
product inputs and fixtures; they never exclude product bytes from validation.

Image adapters support JPEG/JFIF, PNG/APNG, GIF, WebP, AVIF, BMP, ICO, TIFF,
HEIC/HEIF and safe SVG. Active SVG cannot be previewed. Only registered sources
are served. Downloads preserve original bytes with attachment disposition and
sandbox headers; generic originals use `/api/artifact` as opaque downloads.

When a new artifact has a supported image extension, Hub checks its format from
the supplied bytes before saving its reference. For example, JPEG bytes supplied
as `capture.png` receive the name `capture.jpg`; the descriptor retains the
supplied name in `originalName`. The bytes and the original local file remain
unchanged. Correctly named images keep their names. Other files retain their
names and their existing preview limits. Older immutable references keep working
with their original names because previews also detect the actual format.

## Preview decoders

Install optional preview dependencies into the Python environment running Hub:

```powershell
python -m pip install -r requirements-images.txt
```

Pillow supplies raster thumbnails and TIFF conversion; pillow-heif adds HEIC
and HEIF. Without these decoders browser-native formats still work, and other
originals remain downloadable with an explicit unavailable-preview state.
Preview conversion must not alter originals. For multipage images the preview
shows the first page; the complete file remains available for download.

Decoder documentation: [Pillow formats](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html)
and [pillow-heif registration](https://pillow-heif.readthedocs.io/en/stable/pillow-plugin.html).

## Agent API

Create the task/stage first, then read its revision and call:

```text
hub_image(task, path="docs/artifacts/example.webp", expected=revision,
          label="Layout after the fix", stage="verification")
```

Omit `stage` for a direct task source. With `stage`, one stage evidence update
also makes the image discoverable in the combined task gallery. Existing
sources, stage results and provenance remain intact. Conflicting revisions
require a fresh read. Repeating an existing attachment with the current
revision is a no-op. Include the path in the corresponding report evidence.
`hub_memory(ref="source:<path>")` returns image metadata and a hash instead of
decoding binary image bytes as text. Transferred sources retain their original
project and current/archive selection.

For any-format immutable evidence, call `hub_artifact(task, path, expected,
stage?, label?, roles?, previous?)`. A project-relative original is snapshotted
outside checkout and remains unchanged in the product input tree. An existing
upload reference can be attached directly. `previous` explicitly continues an
already registered version with the same artifact ID. Repeating the same
attachment with a fresh revision is a no-op. Binary memory reads return metadata
and hashes; inspect supported previews or download the exact original.

Use the returned `source.path` when attaching a new upload: an image extension
may have been corrected. When saving a screenshot from a browser or another
tool, use the format actually returned by that tool. Giving JPEG bytes a `.png`
filename does not convert them into PNG.

## Further improvements

Useful follow-ups are image captions and alt text as separate fields, explicit
before/after comparison, annotations stored separately from the original, and
an image history that connects revised versions. Larger collections would
benefit from filtering by stage and format, and from a disk preview cache with
a size budget and content-hash invalidation. Multipage TIFF navigation should
remain distinct from switching between attached files.
