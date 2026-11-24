"""Execute the unmodified bundled x86 AquesTalk1 DLL on ARM macOS.
Unicorn executes original synthesis instructions. Only imported C string/allocation
functions and DisableThreadLibraryCalls are host shims; no replacement TTS.
Copyright of DLL remains AQUEST Corp; preserve accompanying AqLicence.txt.
"""
import struct,hashlib,wave,io,argparse
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EIP,UC_X86_REG_ESP,UC_X86_REG_EAX
KNOWN={'454784d7e74cca22b8af90c52967818bfb43a4e072d129abd70e9f7d3a3e76cb','d5b2f85bc260bb5f55cd8d09a6f99fc7a0799af9f4e7287df1e43dcc238d16fe'}
class Engine:
 def __init__(self,dll):
  self.sha=hashlib.sha256(Path(dll).read_bytes()).hexdigest()
  if self.sha not in KNOWN:raise ValueError('Unreviewed DLL')
  self.pe=pefile.PE(str(dll));self.base=self.pe.OPTIONAL_HEADER.ImageBase;self.uc=Uc(UC_ARCH_X86,UC_MODE_32);self.heap=0x30000000;self.cursor=self.heap;self.strtok_pos=0;self.calls={}
  for addr,size in [(0,0x10000),(self.base,(self.pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095),(0x20000000,0x20000),(self.heap,0x4000000),(0x70000000,0x200000)]:self.uc.mem_map(addr,size)
  self.uc.mem_write(0,struct.pack("<I",0xffffffff));self.uc.mem_write(self.base,self.pe.get_memory_mapped_image());self.uc.mem_write(0x20010000,b'\x90');self.hooks={}
  n=0
  for mod in self.pe.DIRECTORY_ENTRY_IMPORT:
   for imp in mod.imports:
    addr=0x20000000+n*16;n+=1;name=imp.name.decode();self.hooks[addr]=name;self.uc.mem_write(imp.address,struct.pack('<I',addr));self.uc.mem_write(addr,b'\xc3')
  self.uc.hook_add(UC_HOOK_CODE,self.hook,begin=0x20000000,end=0x20001000)
  self.exports={e.name.decode():self.base+e.address for e in self.pe.DIRECTORY_ENTRY_EXPORT.symbols}
  self.invoke(self.base+self.pe.OPTIONAL_HEADER.AddressOfEntryPoint,[self.base,1,0])
 def alloc(self,n):
  n=max(16,n);addr=self.cursor;self.cursor=(addr+n+15)&~15
  if self.cursor>=self.heap+0x4000000:raise MemoryError('Emulated heap full')
  return addr
 def u32(self,a):return struct.unpack('<I',self.uc.mem_read(a,4))[0]
 def string(self,a,limit=200000):
  if not a:return b''
  data=bytes(self.uc.mem_read(a,min(limit,0x1000)))
  while b'\0' not in data and len(data)<limit:data+=bytes(self.uc.mem_read(a+len(data),min(4096,limit-len(data))))
  return data.split(b'\0',1)[0]
 def hook(self,uc,addr,size,user):
  name=self.hooks.get(addr)
  if not name:return
  self.calls[name]=self.calls.get(name,0)+1;esp=uc.reg_read(UC_X86_REG_ESP);ret=self.u32(esp);arg=lambda n:self.u32(esp+4+4*n);val=0;stdcall=0
  if name=='malloc':val=self.alloc(arg(0))
  elif name=='free':pass
  elif name=='DisableThreadLibraryCalls':val=1;stdcall=4
  elif name=='_adjust_fdiv':val=0
  elif name=='_initterm':
   funcs=[self.u32(p) for p in range(arg(0),arg(1),4) if self.u32(p)]
   if funcs:
    code=b''.join(b'\xb8'+struct.pack('<I',f)+b'\xff\xd0' for f in funcs)+b'\xc3';stub=self.alloc(len(code));uc.mem_write(stub,code);uc.reg_write(UC_X86_REG_EIP,stub);return
  elif name in ('strncmp','_stricmp'):
   if name=='strncmp':n=arg(2);a=self.string(arg(0),n);b=self.string(arg(1),n)
   else:a=self.string(arg(0)).lower();b=self.string(arg(1)).lower()
   val=(a>b)-(a<b)
  elif name=='strncpy':
   dst,src,n=arg(0),arg(1),arg(2);s=self.string(src,n);uc.mem_write(dst,s[:n]+b'\0'*max(0,n-len(s)));val=dst
  elif name=='strchr':
   a=arg(0);s=self.string(a)+b'\0';pos=s.find(bytes([arg(1)&255]));val=a+pos if pos>=0 else 0
  elif name=='strtok':
   a=arg(0) or self.strtok_pos;delims=self.string(arg(1))
   if a:
    s=self.string(a);i=0
    while i<len(s) and s[i] in delims:i+=1
    if i==len(s):self.strtok_pos=0
    else:
     j=i
     while j<len(s) and s[j] not in delims:j+=1
     val=a+i
     if j<len(s):uc.mem_write(a+j,b'\0');self.strtok_pos=a+j+1
     else:self.strtok_pos=0
  else:raise RuntimeError('Unsupported import '+name)
  uc.reg_write(UC_X86_REG_EAX,val&0xffffffff);uc.reg_write(UC_X86_REG_ESP,esp+4+stdcall);uc.reg_write(UC_X86_REG_EIP,ret)
 def invoke(self,addr,args):
  stack=0x701ff000;self.uc.mem_write(stack,struct.pack('<'+'I'*(len(args)+1),0x20010000,*args));self.uc.reg_write(UC_X86_REG_ESP,stack)
  self.uc.emu_start(addr,0x20010000,timeout=60000000)
  if self.uc.reg_read(UC_X86_REG_EIP)!=0x20010000:raise TimeoutError('DLL call did not return')
  return self.uc.reg_read(UC_X86_REG_EAX)
 def synth(self,kana,speed=120):
  # Reset only transient allocation, preserving initialized DLL globals.
  self.cursor=self.heap+0x10000;data=kana.translate(str.maketrans({'づ':'ず','ぢ':'じ','ヅ':'ズ','ヂ':'ジ'})).encode('cp932')+b'\0';text=self.alloc(len(data));self.uc.mem_write(text,data);size=self.alloc(4);self.uc.mem_write(size,b'\0'*4)
  p=self.invoke(self.exports['AquesTalk_Synthe'],[text,speed,size]);n=self.u32(size)
  if not p:raise ValueError(f'AquesTalk error {n}: {kana[:160]}')
  data=bytes(self.uc.mem_read(p,n));self.invoke(self.exports['AquesTalk_FreeWave'],[p])
  with wave.open(io.BytesIO(data),'rb') as w:
   if w.getsampwidth()!=2 or w.getnchannels()!=1 or w.getframerate()!=8000 or w.getnframes()==0:raise ValueError('Unexpected native WAV')
  return data
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('dll');p.add_argument('kana');p.add_argument('wav');a=p.parse_args();e=Engine(a.dll);Path(a.wav).write_bytes(e.synth(a.kana));print({'dll_sha256':e.sha,'bytes':Path(a.wav).stat().st_size,'imports':e.calls})
