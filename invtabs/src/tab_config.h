#pragma once
// Core: ParseTabs + ParseTypes after custom tables load, Validate before leasing;
// Matches at item-policy checks. Standard library only; no game/SDK dependency.
#include <algorithm>
#include <string>
#include <sstream>
#include <vector>
#include <set>

namespace invtabs {
struct Tab { std::string name, label, typesFile; int columns=0, rows=0, x=-1, y=-1; std::vector<std::string> types; };
struct TypeRow { std::string code, equiv1, equiv2; };
inline bool Token(const std::string& s) {
    if (s.empty()) return false;
    for (unsigned char c:s) if (!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-')) return false;
    return true;
}
inline bool Code(const std::string& s) {
    if (s.empty()||s.size()>4) return false;
    for (unsigned char c:s) if(c<33||c>=127) return false;
    return true;
}
inline bool Fail(std::string& error, const char* message) { error=message; return false; }
inline bool Lines(const std::string& text, const std::string& header, std::vector<std::string>& lines, std::string& error) {
    lines.clear();
    if(text.empty()||text.back()!='\n'||text.find('\r')!=std::string::npos) return Fail(error,"expected LF TSV with final newline");
    std::istringstream in(text); std::string line;
    if(!std::getline(in,line)||line!=header) return Fail(error,"invalid TSV header");
    while(std::getline(in,line)) lines.push_back(line);
    return true;
}
inline bool ParseTypes(const std::string& text, Tab& tab, std::string& error) {
    std::vector<std::string> codes;
    if(!Lines(text,"itemType",codes,error)) return false;
    std::set<std::string> seen;
    if(codes.empty()) return Fail(error,"empty types table");
    for(const auto& code:codes) if(!Code(code)||!seen.insert(code).second) return Fail(error,"invalid or duplicate type code");
    tab.types=codes; return true;
}
inline bool Dimension(const std::string& s, int& value) {
    value=0; if(s.empty()||s.size()>2) return false;
    for(char c:s) { if(c<'0'||c>'9') return false; value=value*10+c-'0'; }
    return value>=1&&value<=16;
}
inline bool ParseTabs(const std::string& text, std::vector<Tab>& tabs, std::string& error) {
    std::vector<std::string> lines; std::vector<Tab> parsed; std::set<std::string> names,files;
    if(!Lines(text,"name\tlabel\tcolumns\trows\ttypes",lines,error)) return false;
    if(lines.empty()||lines.size()>12) return Fail(error,"expected 1..12 tabs");
    for(const auto& line:lines) {
        std::vector<std::string> fields; size_t at=0,next;
        do { next=line.find('\t',at); fields.push_back(line.substr(at,next==std::string::npos?next:next-at)); at=next+1; } while(next!=std::string::npos);
        if(fields.size()!=5) return Fail(error,"invalid tab columns");
        Tab t; t.name=fields[0]; t.label=fields[1]; t.typesFile=fields[4];
        if(!Token(t.name)||!names.insert(t.name).second) return Fail(error,"invalid or duplicate tab name");
        if(t.label.empty()) return Fail(error,"empty label");
        for(unsigned char c:t.label) if(c<32||c>=127) return Fail(error,"invalid label");
        const auto& f=t.typesFile;
        if(f.size()<=10||f.substr(0,6)!="types_"||f.substr(f.size()-4)!=".txt"||!Token(f.substr(6,f.size()-10))||!files.insert(f).second) return Fail(error,"invalid or duplicate types file");
        if(!Dimension(fields[2],t.columns)||!Dimension(fields[3],t.rows)) return Fail(error,"tab dimensions outside 1..16");
        parsed.push_back(t);
    }
    tabs=parsed; return true;
}
// Fresh packing follows wild-healer's aaa-player-page-host: stable area/height
// descending, first free y/x, no rotation. Saved placements remain the host's job.
inline bool Pack(std::vector<Tab>& tabs, std::string& error) {
    if(tabs.empty()||tabs.size()>12) return Fail(error,"expected 1..12 tabs");
    std::vector<size_t> order;
    for(size_t i=0;i<tabs.size();++i) {
        auto& t=tabs[i]; t.x=t.y=-1;
        if(t.columns<1||t.columns>16||t.rows<1||t.rows>16) return Fail(error,"tab dimensions outside 1..16");
        order.push_back(i);
    }
    std::stable_sort(order.begin(),order.end(),[&](size_t a,size_t b){
        const auto& x=tabs[a]; const auto& y=tabs[b];
        return x.columns*x.rows!=y.columns*y.rows ? x.columns*x.rows>y.columns*y.rows : x.rows>y.rows;
    });
    bool used[16][16]={}; auto packed=tabs;
    for(auto i:order) {
        auto& t=packed[i]; bool placed=false;
        for(int y=0;y<=16-t.rows&&!placed;++y) for(int x=0;x<=16-t.columns&&!placed;++x) {
            bool free=true;
            for(int cy=y;cy<y+t.rows;++cy) for(int cx=x;cx<x+t.columns;++cx) if(used[cy][cx]) free=false;
            if(!free) continue;
            for(int cy=y;cy<y+t.rows;++cy) for(int cx=x;cx<x+t.columns;++cx) used[cy][cx]=true;
            t.x=x; t.y=y; placed=true;
        }
        if(!placed) return Fail(error,"tabs do not fit the 16 x 16 page");
    }
    tabs=packed; return true;
}
// Accessor: bool(const std::string& code, TypeRow& out). Unknown rows fail
// closed; visited codes bound cycles and diamonds without a recursion limit.
template<class Accessor> bool Matches(const Tab& tab, const std::string& code, Accessor row) {
    std::vector<std::string> pending{code}; std::set<std::string> seen;
    while(!pending.empty()) {
        auto current=pending.back(); pending.pop_back();
        if(current.empty()||!seen.insert(current).second) continue;
        TypeRow r; if(!row(current,r)) continue;
        if(std::find(tab.types.begin(),tab.types.end(),current)!=tab.types.end()) return true;
        pending.push_back(r.equiv1); pending.push_back(r.equiv2);
    }
    return false;
}
template<class Accessor> bool Validate(std::vector<Tab>& tabs, Accessor row, std::string& error) {
    for(const auto& t:tabs) {
        if(t.types.empty()) return Fail(error,"empty types table");
        std::set<std::string> seen;
        for(const auto& code:t.types) { TypeRow r;
            if(!Code(code)||!seen.insert(code).second||!row(code,r)) return Fail(error,"unknown or duplicate type code");
        }
    }
    return Pack(tabs,error);
}
inline Tab CharmFallback() {
    Tab t; t.name="charms"; t.label="Charms"; t.typesFile="types_charms.txt"; t.columns=10; t.rows=6; t.types={"char"}; return t;
}
} // namespace invtabs
