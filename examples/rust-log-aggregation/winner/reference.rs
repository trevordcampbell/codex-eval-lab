use std::collections::BTreeMap;
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Row { pub endpoint: String, pub count: u64, pub errors: u64, pub bytes: u128 }
#[derive(Debug, PartialEq, Eq)]
pub struct Output { pub rows: Vec<Row>, pub invalid: u64 }
// Contract: UTF-8 input; lines separated by LF, optional single terminal CR.
// Exactly 3 TAB-separated fields; nonempty endpoint starting '/' and no controls.
// ASCII digits only; status 100..599; bytes 0..u64::MAX; u128 aggregate sum.
// Empty input has no rows. A final LF terminates rather than adds an empty row.
pub fn aggregate(input: &str) -> Output {
    let mut map: BTreeMap<String, (u64,u64,u128)> = BTreeMap::new();
    let mut invalid = 0;
    for raw in input.split_terminator('\n') {
        let line = raw.strip_suffix('\r').unwrap_or(raw);
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.len() != 3 || !parts[0].starts_with('/') || parts[0].chars().any(|c| c.is_control()) ||
            parts[1].is_empty() || parts[2].is_empty() ||
            !parts[1].bytes().all(|b| b.is_ascii_digit()) || !parts[2].bytes().all(|b| b.is_ascii_digit()) {
            invalid += 1; continue;
        }
        let (Ok(status),Ok(bytes)) = (parts[1].parse::<u64>(), parts[2].parse::<u64>()) else { invalid += 1; continue; };
        if !(100..=599).contains(&status) { invalid += 1; continue; }
        let item = map.entry(parts[0].to_owned()).or_insert((0,0,0));
        item.0 += 1; item.1 += u64::from(status >= 400); item.2 += bytes as u128;
    }
    Output { rows: map.into_iter().map(|(endpoint,(count,errors,bytes))| Row { endpoint,count,errors,bytes }).collect(), invalid }
}
