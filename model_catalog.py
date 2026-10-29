"""Explicit model identities, voices and license boundaries."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CIS_PATH = ROOT / 'models' / 'v5_cis_base.pt'
RU_PATH = ROOT / 'models' / 'silero-v5_ru.pt'
CIS_VOICES = tuple(sorted('bak_aigul ru_aigul tat_albina ru_albina erz_alexandr ru_alexandr bak_alfia ru_alfia bak_alfia2 ru_alfia2 bel_anatoliy udm_bogdan ru_bogdan bel_dmitriy ru_dmitriy chv_ekaterina ru_ekaterina kat_vika ru_vika aze_gamat ru_gamat ukr_igor ru_igor kjh_karina ru_karina xal_kejilgan ru_kejilgan xal_kermen ru_kermen bel_larisa tat_marat ru_marat bak_miyau ru_miyau kir_nurgul ru_nurgul mdf_oksana ru_oksana tgk_onaoy ru_onaoy bak_ramilia ru_ramilia ukr_roman ru_roman tgk_safarhuja ru_safarhuja uzb_saida ru_saida kjh_sibday ru_sibday hye_zara ru_zara kaz_zhadyra ru_zhadyra kaz_zhazira ru_zhazira sah_zinaida ru_zinaida ru_eduard kbd_eduard'.split(), key=lambda voice: (not voice.startswith('ru_'), voice)))
RU_VOICES = ('kseniya', 'xenia', 'baya', 'aidar', 'eugene')
DEFAULT_SPEAKER = 'ru_zhadyra'
CIS_LABEL = 'v5_cis_base · MIT'
RU_LABEL = 'v5_ru · некоммерческая'
