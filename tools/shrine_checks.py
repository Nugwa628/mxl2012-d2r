"""Shrine colours: harness-made items, background MEDIAN stash deposit/hover.
Uses a fresh lane character; pictures and tooltip text need visual review.
"""
import time
import os
import elixir_colours
import medtab_checks as mt
import median_tabs
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


def run_tips(gc):
    """Lane shrinetip: every shrine kind hovered in the backpack and on MEDIAN, part-charged ones, the elixir rows."""
    mark = gc.engine_mark()
    log, shots, bad = [], [], []
    gc.goto(1)
    gc.set_graphics('hd')
    gc.close_right_panel()
    gc.H('packclear')
    if not gc.sp2_open_stash(log):
        gc.finish('shrinetip', False, 'stash did not open', mark, shots, log)
        return
    mt.tab(gc, 'median')
    for code in elixir_colours.CODES:
        if not mt.ctrl_move(gc, log, code):
            bad.append(f'{code}: not deposited')
    for mode in ('hd', 'legacy'):
        legacy = mode == 'legacy'
        gc.set_graphics(mode)
        time.sleep(1)
        lay = st.layout(gc, legacy)
        mt.tab(gc, 'median')
        st.park(gc)
        shots.append(gc.sh(f'shrinetip_{mode}_elixirs'))
        for code in median_tabs.SHRINES:
            if not st.one(gc, log, shots, mode, 'median', code, lay, legacy, prefix='shrinetip'):
                bad.append(f'{mode} {code}: not hovered')
        for code in ('eo7', '0g6'):
            xy = st.slot_xy(gc, lay, 'advancedstash_runes', code, legacy)
            if xy:
                st.hover(gc, xy)
                shots.append(gc.sh(f'shrinetip_{mode}_elixir_{code}'))
        grid = mt.SD_INV if legacy else gc.RP_INV
        for code in ('A5+', 'T9+'):
            before = mt.backpack_ids(gc)
            gc.Hl(f'item {code} inv', log)
            time.sleep(0.6)
            new = [i for i in gc.rp_items_now() if i.get('page') == 0 and i['id'] not in before]
            if new:
                st.hover(gc, gc.rp_inv_xy(new[0]['x'], new[0]['y'], grid))
                shots.append(gc.sh(f'shrinetip_{mode}_partial_{code[0]}'))
            else:
                bad.append(f'{mode} {code}: not made')
        st.park(gc)
    gc.set_graphics('hd')
    gc.close_right_panel()
    gc.H('packclear')
    gc.finish('shrinetip', not bad, '; '.join(bad) or '20 shrine kinds hovered, 22 elixirs on MEDIAN; SHORTCUT harness item creation; REVIEW tooltips and colours',
              mark, shots, log, partial='visual tooltip/colour review')


def run_lines(gc):
    """Lane shrineline: the Cube line on all 20 kinds and part-charged ones, in the backpack. Legacy first, with no stash in the way
    (a switch with the stash open once left it closed); then HD, plus the same line on three MEDIAN slots."""
    mark = gc.engine_mark()
    log, shots, bad = [], [], []
    gc.goto(1)
    gc.close_right_panel()
    for mode in ('legacy', 'hd'):
        legacy = mode == 'legacy'
        if not gc.set_graphics(mode):
            bad.append(f'{mode}: graphics not reached')
            continue
        time.sleep(1)
        gc.H('packclear')
        gc.g.press('i')
        time.sleep(1.2)
        grid = mt.SD_INV if legacy else gc.RP_INV
        made = {}
        for code in median_tabs.SHRINES + ['A5+', 'T9+']:
            before = mt.backpack_ids(gc)
            gc.Hl(f'item {code} inv', log)
            time.sleep(0.4)
            new = [i for i in gc.rp_items_now() if i.get('page') == 0 and i['id'] not in before]
            if new:
                made[code] = new[0]
            else:
                bad.append(f'{mode} {code}: not made')
        st.park(gc)
        shots.append(gc.sh(f'shrineline_{mode}_ref'))
        for code, it in made.items():
            xy = gc.rp_inv_xy(it['x'], it['y'], grid)
            st.hover(gc, xy)
            log.append(f'{mode} {code}: {xy[0] * 1600:.0f},{xy[1] * 900:.0f}')
            shots.append(gc.sh(f'shrineline_{mode}_{code[0]}{code[1]}'))
        st.park(gc)
        gc.g.press('i')
        time.sleep(1.0)
    if gc.sp2_open_stash(log):
        lay = st.layout(gc, False)
        for code in ('A0+', 'L0+', 'T0+'):
            if not st.one(gc, log, shots, 'hd', 'median', code, lay, False, prefix='shrineline'):
                bad.append(f'hd {code}: MEDIAN slot not hovered')
        gc.close_right_panel()
    else:
        bad.append('stash did not open')
    gc.H('packclear')
    gc.finish('shrineline', not bad, '; '.join(bad) or '20 shrine kinds + 2 part-charged, HD and legacy, backpack; 3 MEDIAN slots in HD; REVIEW text and wrap on the shots',
              mark, shots, log, partial='visual review of the tooltip line')
