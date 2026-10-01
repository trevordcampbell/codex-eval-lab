use std::collections::HashMap;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Row {
    pub endpoint: String,
    pub count: u64,
    pub errors: u64,
    pub bytes: u128,
}

#[derive(Debug, PartialEq, Eq)]
pub struct Output {
    pub rows: Vec<Row>,
    pub invalid: u64,
}

#[inline]
fn parse_bytes(text: &[u8]) -> Option<u64> {
    if text.is_empty() {
        return None;
    }
    let mut value = 0u64;
    if text.len() <= 19 {
        // Every sequence of at most 19 decimal digits fits in u64. Validate
        // and accumulate together without overflow checks on this path.
        for &byte in text {
            let digit = byte.wrapping_sub(b'0');
            if digit > 9 {
                return None;
            }
            value = value * 10 + u64::from(digit);
        }
    } else {
        // Arbitrarily many leading zeroes are valid. Length alone cannot
        // reject a field, so use checked arithmetic for longer strings.
        for &byte in text {
            let digit = byte.wrapping_sub(b'0');
            if digit > 9 {
                return None;
            }
            value = value.checked_mul(10)?.checked_add(u64::from(digit))?;
        }
    }
    Some(value)
}

#[inline]
fn parse_record(line: &str) -> Option<(&str, bool, u64)> {
    let text = line.as_bytes();
    if text.first().copied() != Some(b'/') {
        return None;
    }

    // Find the first separator while checking the ASCII endpoint grammar.
    // A TAB is an ASCII character boundary, so slicing there is UTF-8 safe.
    let mut pos = 1;
    let mut non_ascii = false;
    while pos < text.len() && text[pos] != b'\t' {
        let byte = text[pos];
        if byte < 0x20 || byte == 0x7f {
            return None;
        }
        non_ascii |= !byte.is_ascii();
        pos += 1;
    }
    if pos == text.len() {
        return None;
    }
    let endpoint = &line[..pos];
    if non_ascii && endpoint.chars().any(|c| c.is_control()) {
        return None;
    }

    // The status is bounded by its contract, so accumulating beyond 599
    // can reject immediately. This still accepts any number of leading 0s.
    pos += 1;
    let status_start = pos;
    let mut status = 0u16;
    while pos < text.len() && text[pos] != b'\t' {
        let digit = text[pos].wrapping_sub(b'0');
        if digit > 9 {
            return None;
        }
        status = status * 10 + u16::from(digit);
        if status > 599 {
            return None;
        }
        pos += 1;
    }
    if pos == text.len() || pos == status_start || status < 100 {
        return None;
    }

    // Any additional TAB is rejected by the digit grammar, preserving the
    // exactly-three-fields rule without another delimiter scan.
    let bytes = parse_bytes(&text[pos + 1..])?;
    Some((endpoint, status >= 400, bytes))
}

// Contract: UTF-8 input; lines separated by LF, optional single terminal CR.
// Exactly 3 TAB-separated fields; nonempty endpoint starting '/' and no controls.
// ASCII digits only; status 100..599; bytes 0..u64::MAX; u128 aggregate sum.
// Empty input has no rows. A final LF terminates rather than adds an empty row.
pub fn aggregate(input: &str) -> Output {
    // Borrow endpoint keys and retain the standard randomized hasher for
    // untrusted log input. No data is cached across calls.
    let mut map: HashMap<&str, (u64, u64, u128)> = HashMap::new();
    let mut invalid = 0;

    for raw in input.split_terminator('\n') {
        let line = raw.strip_suffix('\r').unwrap_or(raw);
        let Some((endpoint, is_error, bytes)) = parse_record(line) else {
            invalid += 1;
            continue;
        };
        let item = map.entry(endpoint).or_insert((0, 0, 0));
        item.0 += 1;
        item.1 += u64::from(is_error);
        item.2 += bytes as u128;
    }

    let mut rows: Vec<Row> = map
        .into_iter()
        .map(|(endpoint, (count, errors, bytes))| Row {
            endpoint: endpoint.to_owned(),
            count,
            errors,
            bytes,
        })
        .collect();
    rows.sort_unstable_by(|a, b| a.endpoint.cmp(&b.endpoint));
    Output { rows, invalid }
}
