-- Take out the line columns 0053 added. Nothing reads them.
--
-- 0053 split "which line reaches this street" from "how fast it is claimed to be", because
-- capping the figure at what the operator filed means the number no longer names the line:
-- a vectored cabinet filed "2-10 Mbps" is worth 10, and so is an ADSL one filed the same
-- way. That reasoning still holds, and it is why a map cannot be coloured by technology and
-- by speed at the same time. The map is coloured by speed, so the line is not needed.
--
-- Dropping rank also drops a subtle wrong answer it was producing. Picking each operator's
-- best LINE and then that line's figure understates what the operator can actually sell:
-- where a filing caps vectoring to 10 and leaves that operator's VDSL at 50, the reader can
-- have 50, and rank-first reported 10. A plain maximum over the figures is both simpler and
-- the honest reading of "the best you can get here from this operator".
alter table street drop column if exists best_line;
alter table street_provider drop column if exists line;
alter table technology drop column if exists rank;
