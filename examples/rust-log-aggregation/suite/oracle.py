"""Independent declarative oracle, not a translation of candidate implementation."""
import re, unicodedata
PATTERN = re.compile(r'([^\t]*)\t([0-9]+)\t([0-9]+)\Z')
MAX_U64 = (1 << 64) - 1

def oracle(text):
    counts={}; invalid=0
    lines=text.split('\n')
    if lines[-1]=='':lines.pop()
    for raw in lines:
        line=raw[:-1] if raw.endswith('\r') else raw
        match=PATTERN.fullmatch(line)
        if not match:
            invalid+=1; continue
        path,code,size=match.groups()
        code=code.lstrip('0') or '0'; size=size.lstrip('0') or '0'
        if len(code)>3 or len(size)>20:
            invalid+=1; continue
        code=int(code); size=int(size)
        if not path.startswith('/') or any(unicodedata.category(c)=='Cc' for c in path) or not 100<=code<=599 or size>MAX_U64:
            invalid+=1; continue
        row=counts.setdefault(path,[0,0,0]); row[0]+=1;row[1]+=code>=400;row[2]+=size
    return {'invalid':invalid,'rows':[[k,*v] for k,v in sorted(counts.items())]}
