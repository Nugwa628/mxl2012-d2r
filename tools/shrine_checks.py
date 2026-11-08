"""Shrine colours: harness-made items, background MEDIAN stash deposit/hover.
Uses a fresh lane character; pictures and tooltip text need visual review.
"""
import time
import os
import medtab_checks as mt
import stashtip_checks as st


def run(gc):
    mark = gc.engine_mark()
    log, shots, bad = [], [], []
    gc.goto(1)
    gc.set_graphics('hd')
    gc.close_right_panel()
    gc.H('packclear')
    if not gc.sp2_open_stash(log):
        gc.finish('shrinecol', False, 'stash did not open', mark, shots, log)
        return
    mt.tab(gc, 'median')
    for i in range(0 if os.environ.get('MXL_SHRINE_REUSE') == '1' else 20):
        code = f'{chr(65+i)}0+'
        if not mt.ctrl_move(gc, log, code):
            bad.append(f'{code}: not deposited')
    for mode in ('hd', 'legacy'):
        gc.set_graphics(mode)
        # The open panel survives G; right_panel_open's HD close-button heuristic
        # cannot detect a classic inventory and would start a needless walk.
        mt.tab(gc, 'median')
        st.park(gc)
        shots.append(gc.sh('shrinecol_' + mode + '_all20'))
        status = mt.status(gc, log)
        if status.get('tab') != 5 or not status.get('live'):
            bad.append(mode + ': MEDIAN tab not live')
        lay = st.layout(gc, mode == 'legacy')
        for code in ('A0+', 'T0+'):
            xy = st.slot_xy(gc, lay, 'advancedstash_runes', code, mode == 'legacy')
            if xy:
                st.hover(gc, xy)
                shots.append(gc.sh('shrinecol_' + mode + '_tooltip_' + code[0]))
        st.park(gc)
    gc.set_graphics('hd')
    gc.close_right_panel()
    for code in ('A0+', 'F0+', 'M0+', 'T0+'):
        gc.Hl('item ' + code + ' ground', log)
    for mode in ('hd', 'legacy'):
        gc.set_graphics(mode)
        time.sleep(1)
        shots.append(gc.sh('shrinecol_' + mode + '_ground_art'))
        gc.g._set_mods(('alt',))
        gc.g._post_key(gc.g.need_window(), 'alt', False)
        try:
            time.sleep(1)
            shots.append(gc.sh('shrinecol_' + mode + '_ground'))
        finally:
            gc.g._post_key(gc.g.need_window(), 'alt', True)
            gc.g._set_mods(())
    gc.set_graphics('hd')
    gc.finish('shrinecol', not bad, '; '.join(bad) or '20 shrine types shown; SHORTCUT harness item creation; REVIEW colours, tooltips and ground',
              mark, shots, log, partial='visual colour/tooltip/ground review')
