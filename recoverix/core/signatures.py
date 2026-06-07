"""File signature database and compiled lookups for the carving engine.

The definitions are embedded in code (single source of truth) so they are always
available in a single-file build. ``resources/signatures.json`` mirrors them for
documentation purposes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# type -> definition. Header/footer values are hex strings (case-insensitive).
SIGNATURE_DB: Dict[str, dict] = {
    # Images
    "jpg":    {"category": "Images",    "extensions": ["jpg", "jpeg"],          "headers": ["FFD8FF"],                         "footers": ["FFD9"],            "maxSizeMB": 100},
    "png":    {"category": "Images",    "extensions": ["png"],                  "headers": ["89504E470D0A1A0A"],               "footers": ["49454E44AE426082"], "maxSizeMB": 100},
    "gif":    {"category": "Images",    "extensions": ["gif"],                  "headers": ["474946383761", "474946383961"],  "footers": ["003B"],            "maxSizeMB": 50},
    "bmp":    {"category": "Images",    "extensions": ["bmp"],                  "headers": ["424D"],                           "footers": [],                  "maxSizeMB": 50},
    "tiff":   {"category": "Images",    "extensions": ["tif", "tiff"],          "headers": ["49492A00", "4D4D002A"],          "footers": [],                  "maxSizeMB": 200},
    "webp":   {"category": "Images",    "extensions": ["webp"],                 "headers": ["52494646"],                       "footers": [],                  "maxSizeMB": 50,   "riff": "WEBP"},

    # Documents
    "pdf":    {"category": "Documents", "extensions": ["pdf"],                  "headers": ["25504446"],                       "footers": ["2525454F46", "0A2525454F46", "0D0A2525454F46"], "maxSizeMB": 500},
    "doc":    {"category": "Documents", "extensions": ["doc"],                  "headers": ["D0CF11E0A1B11AE1"],               "footers": [],                  "maxSizeMB": 200},
    "ooxml":  {"category": "Documents", "extensions": ["docx", "xlsx", "pptx", "zip"], "headers": ["504B0304"],               "footers": ["504B0506"],        "maxSizeMB": 500},
    "rtf":    {"category": "Documents", "extensions": ["rtf"],                  "headers": ["7B5C72746631"],                   "footers": ["7D00", "7D"],      "maxSizeMB": 50},

    # Archives
    "rar":    {"category": "Archives",  "extensions": ["rar"],                  "headers": ["526172211A0700", "526172211A070100"], "footers": [],            "maxSizeMB": 2000},
    "7z":     {"category": "Archives",  "extensions": ["7z"],                   "headers": ["377ABCAF271C"],                   "footers": [],                  "maxSizeMB": 2000},
    "gz":     {"category": "Archives",  "extensions": ["gz"],                   "headers": ["1F8B08"],                         "footers": [],                  "maxSizeMB": 1000},

    # Audio
    "mp3":    {"category": "Audio",     "extensions": ["mp3"],                  "headers": ["494433"],                         "footers": [],                  "maxSizeMB": 100},
    "wav":    {"category": "Audio",     "extensions": ["wav"],                  "headers": ["52494646"],                       "footers": [],                  "maxSizeMB": 500,  "riff": "WAVE"},
    "flac":   {"category": "Audio",     "extensions": ["flac"],                 "headers": ["664C6143"],                       "footers": [],                  "maxSizeMB": 500},

    # Video
    "mp4":    {"category": "Video",     "extensions": ["mp4", "m4a", "mov"],    "headers": [],                                 "footers": [],                  "maxSizeMB": 4000, "ftyp": True},
    "avi":    {"category": "Video",     "extensions": ["avi"],                  "headers": ["52494646"],                       "footers": [],                  "maxSizeMB": 4000, "riff": "AVI "},
    "mkv":    {"category": "Video",     "extensions": ["mkv", "webm"],          "headers": ["1A45DFA3"],                       "footers": [],                  "maxSizeMB": 4000},
    "wmv":    {"category": "Video",     "extensions": ["wmv", "asf"],           "headers": ["3026B2758E66CF11"],               "footers": [],                  "maxSizeMB": 4000},

    # Databases
    "sqlite": {"category": "Databases", "extensions": ["sqlite", "db"],         "headers": ["53514C69746520666F726D6174203300"], "footers": [],          "maxSizeMB": 1000},
}


@dataclass
class Signature:
    key: str
    category: str
    extension: str
    headers: List[bytes]
    footers: List[bytes]
    max_size: int
    riff: Optional[str] = None
    ftyp: bool = False

    @property
    def primary_extension(self) -> str:
        return self.extension


def _hex(values: List[str]) -> List[bytes]:
    return [bytes.fromhex(v) for v in values]


def load_signatures() -> List[Signature]:
    """Return compiled signatures (byte patterns) ready for scanning."""
    sigs: List[Signature] = []
    for key, d in SIGNATURE_DB.items():
        sigs.append(
            Signature(
                key=key,
                category=d["category"],
                extension=d["extensions"][0],
                headers=_hex(d.get("headers", [])),
                footers=_hex(d.get("footers", [])),
                max_size=int(d.get("maxSizeMB", 100)) * 1024 * 1024,
                riff=d.get("riff"),
                ftyp=bool(d.get("ftyp", False)),
            )
        )
    return sigs


def categories() -> List[str]:
    return sorted({d["category"] for d in SIGNATURE_DB.values()})
