-- Operators answer with three numbers per direction, not one. The average is what the line
-- actually carries and is the honest input to a ranking; the maximum is the headline. Both
-- are kept because both are shown, and the minimum stays in raw where it belongs: it is a
-- worst case, not a speed anyone should be compared on.
alter table availability add avg_down_mbps numeric;
alter table availability add avg_up_mbps numeric;
