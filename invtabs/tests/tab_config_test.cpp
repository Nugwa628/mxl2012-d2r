#include "../src/tab_config.h"
#include <cstdio>
#include <map>
namespace {
int failures=0;
void Check(bool ok,const char* label) { if(!ok) { ++failures; std::printf("FAIL: %s\n",label); } }
void Test() {
    using namespace invtabs;
    std::string error; std::vector<Tab> tabs;
    const std::string head="name\tlabel\tcolumns\trows\ttypes\n";
    Check(ParseTabs(head+"charms\tCharms\t10\t6\ttypes_charms.txt\n",tabs,error),"parse table");
    Check(ParseTypes("itemType\nchar\n",tabs[0],error),"parse types");
    std::map<std::string,TypeRow> rows={{"char",{"char","",""}}, {"deep",{"deep","loop","char"}}, {"loop",{"loop","deep",""}}, {"nope",{"nope","nope",""}}};
    auto row=[&](const std::string& code,TypeRow& out) { auto i=rows.find(code); if(i==rows.end()) return false; out=i->second; return true; };
    Check(Validate(tabs,row,error)&&tabs[0].x==0&&tabs[0].y==0,"validate and pack");
    Check(Matches(tabs[0],"deep",row),"Equiv2 through cycle");
    Check(!Matches(tabs[0],"nope",row)&&!Matches(tabs[0],"absent",row),"cycle and unknown fail closed");
    Check(!ParseTypes("itemType\nchar\nchar\n",tabs[0],error),"duplicate types");
    Check(!ParseTypes("itemType\nabcde\n",tabs[0],error),"long code");
    Check(!ParseTypes("itemType\r\nchar\r\n",tabs[0],error),"strict LF");
    Check(ParseTypes("itemType\nxxxx\n",tabs[0],error)&&!Validate(tabs,row,error),"unknown code");
    for(const auto& size:{"0","17","1junk","-1","99999999999"}) Check(!ParseTabs(head+"a\tA\t"+size+"\t6\ttypes_a.txt\n",tabs,error),"invalid dimension");
    Check(!ParseTabs(head+"a\tA\t1\t1\t../a.txt\n",tabs,error),"unsafe filename");
    const std::string line="a\tA\t1\t1\ttypes_a.txt\n";
    Check(!ParseTabs(head+line+line,tabs,error),"duplicate tab");
    tabs={CharmFallback(),CharmFallback()}; tabs[0].columns=9; tabs[0].rows=9; tabs[1].columns=8; tabs[1].rows=8;
    Check(!Pack(tabs,error),"area fits but rectangles do not");
    tabs={CharmFallback(),CharmFallback()}; tabs[0].columns=6; tabs[0].rows=6; tabs[1].columns=10; tabs[1].rows=16;
    Check(Pack(tabs,error)&&tabs[1].x==0&&tabs[0].x==10,"largest first, no rotation");
    tabs.resize(13); Check(!Pack(tabs,error),"tab count limit");
}
}
int main() { Test(); std::printf("tab_config_test: %d failures\n",failures); return failures?1:0; }
