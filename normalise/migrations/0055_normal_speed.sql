-- The speed the operator says you normally get, as opposed to the most the line can do.
--
-- EETT collects both and we were only carrying one. a4a_maxdown is the maximum download
-- speed; a4a_nordown is the normally available one, on the same eight-band scale, and it is
-- the closer of the two to what somebody actually experiences.
--
-- Checked before taking it, because the note in NEEDTOKNOW had dismissed it as differing in
-- only 5% of rows:
--
--   * It is populated in exactly the rows maxdown is — 364,284 of them — and never alone,
--     so nothing is lost by preferring it and there is no new gap to handle.
--   * It is never HIGHER than maxdown, anywhere. As a cap it can only ever be more
--     conservative, which is the direction this whole figure is supposed to lean.
--   * On copper it sits on average a third of a band below maxdown; on fibre the two are
--     identical, which is why the 5% looked small — fibre is 94% of the filings and has
--     nothing to say here.
--
-- What it buys, measured: the number of streets we can identify as being on 10 Mbps or less
-- nearly doubles, from 2,137 to 3,994. It moves 3,949 streets and every one of them moves
-- down.
--
-- What it does NOT buy, also measured, because it is the question that prompted looking:
-- the 48% of streets sitting at exactly 100 Mbps do not move — 37,180 becomes 37,176. That
-- mass is not the register being read generously. It is vectored VDSL reaching half the
-- country and retailing at 100, and no field in this dataset breaks it up. The granularity
-- the register has is at the bottom of the scale, not in the middle.
alter table coverage add normal_band_id int references speed_band (id);
alter table coverage_area add normal_band_id int references speed_band (id);

comment on column coverage.normal_band_id is
    'a4a_nordown: the normally available speed. speed_band_id is a4a_maxdown, the ceiling.';
comment on column coverage_area.normal_band_id is
    'a4a_nordown: the normally available speed. speed_band_id is a4a_maxdown, the ceiling.';
