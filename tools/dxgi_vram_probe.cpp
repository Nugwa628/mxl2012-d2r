// Lane vramcap (2026-11-21): prints what DXGI tells a game about VRAM (adapter description, IDXGIAdapter3::QueryVideoMemoryInfo
// before and after a D3D12 device and a 512 MB heap). Build with msvc-wine: `cl /nologo /EHsc /O1 dxgi_vram_probe.cpp`; run in
// a slot prefix under Proton with an output path argument (stdout is not passed through), e.g. with env DXVK_CONFIG.
#include <windows.h>
#include <dxgi1_6.h>
#include <d3d12.h>
#include <stdio.h>
#pragma comment(lib,"dxgi.lib")
#pragma comment(lib,"d3d12.lib")
static void q(IDXGIAdapter1*a,const char*when){IDXGIAdapter3*a3=0;if(SUCCEEDED(a->QueryInterface(__uuidof(IDXGIAdapter3),(void**)&a3))){
 DXGI_QUERY_VIDEO_MEMORY_INFO l={},n={};a3->QueryVideoMemoryInfo(0,DXGI_MEMORY_SEGMENT_GROUP_LOCAL,&l);a3->QueryVideoMemoryInfo(0,DXGI_MEMORY_SEGMENT_GROUP_NON_LOCAL,&n);
 printf("%s: local budget %llu MB usage %llu MB avail_resv %llu MB | nonlocal budget %llu MB usage %llu MB\n",when,l.Budget>>20,l.CurrentUsage>>20,l.AvailableForReservation>>20,n.Budget>>20,n.CurrentUsage>>20);a3->Release();}else printf("%s: no IDXGIAdapter3\n",when);}
int main(int c,char**v){if(c>1)freopen(v[1],"w",stdout);IDXGIFactory1*f=0;if(FAILED(CreateDXGIFactory1(__uuidof(IDXGIFactory1),(void**)&f))){printf("no factory\n");return 1;}
 IDXGIAdapter1*a=0;for(UINT i=0;f->EnumAdapters1(i,&a)!=DXGI_ERROR_NOT_FOUND;i++){DXGI_ADAPTER_DESC1 d;a->GetDesc1(&d);
 printf("adapter %u: %ls dedicated %llu MB dedsys %llu MB shared %llu MB flags %u\n",i,d.Description,(unsigned long long)d.DedicatedVideoMemory>>20,(unsigned long long)d.DedicatedSystemMemory>>20,(unsigned long long)d.SharedSystemMemory>>20,d.Flags);
 q(a,"  before d3d12");ID3D12Device*dev=0;HRESULT hr=D3D12CreateDevice(a,D3D_FEATURE_LEVEL_11_0,__uuidof(ID3D12Device),(void**)&dev);printf("  d3d12 device hr=%08lx\n",hr);
 if(dev){ID3D12Heap*h=0;D3D12_HEAP_DESC hd={};hd.SizeInBytes=512ull<<20;hd.Properties.Type=D3D12_HEAP_TYPE_DEFAULT;hd.Flags=D3D12_HEAP_FLAG_ALLOW_ONLY_BUFFERS;
  hr=dev->CreateHeap(&hd,__uuidof(ID3D12Heap),(void**)&h);printf("  512MB heap hr=%08lx\n",hr);q(a,"  after d3d12+512MB");if(h)h->Release();dev->Release();}
 a->Release();}
 f->Release();return 0;}
