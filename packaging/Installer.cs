using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Diagnostics;
using System.Windows.Forms;
class Installer {
 [STAThread] static void Main(string[] args) {
  Application.EnableVisualStyles();
  int waitPid=0; bool restart=false;
  for(int i=0;i<args.Length;i++){
   if(args[i]=="--wait-pid" && i+1<args.Length)Int32.TryParse(args[++i],out waitPid);
   if(args[i]=="--restart")restart=true;
  }
  string root=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","AutoBrightness");
  if(MessageBox.Show("Install Auto Brightness 0.10.1 for your Windows account?\n\nPersonal settings and curves are preserved.\n\n"+root,"Auto Brightness Setup",MessageBoxButtons.OKCancel,MessageBoxIcon.Information)!=DialogResult.OK)return;
  string staging=Path.Combine(Path.GetTempPath(),"AutoBrightness-"+Guid.NewGuid().ToString("N"));
  try {
   if(waitPid>0){try{using(Process previous=Process.GetProcessById(waitPid)){if(!previous.WaitForExit(120000))throw new Exception("The app is still running. Close it and try again.");}}catch(ArgumentException){}}
   Directory.CreateDirectory(staging);
   string zip=Path.Combine(staging,"payload.zip");
   using(Stream source=Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))using(Stream dest=File.Create(zip)){source.CopyTo(dest);}
   string unpack=Path.Combine(staging,"app");
   ZipFile.ExtractToDirectory(zip,unpack);
   if(!File.Exists(Path.Combine(unpack,"AutoBrightness.exe")))throw new Exception("Incomplete installer payload.");
   AutoBrightness.InstallCore.Install(unpack,root,()=>{
   ProcessStartInfo setup=new ProcessStartInfo("powershell.exe","-NoProfile -ExecutionPolicy Bypass -File \""+Path.Combine(root,"RegisterInstall.ps1")+"\" -InstallRoot \""+root+"\"");
   setup.UseShellExecute=false;setup.CreateNoWindow=true;
   using(Process process=Process.Start(setup)){if(!process.WaitForExit(30000)){process.Kill();process.WaitForExit();throw new Exception("Shortcut registration timed out.");}if(process.ExitCode!=0)throw new Exception("Shortcut registration failed.");}
   });
   // Keep one recognized previous installation for an explicit user rollback.
   if(restart || MessageBox.Show("Installation complete. Open Auto Brightness now?","Auto Brightness Setup",MessageBoxButtons.YesNo,MessageBoxIcon.Information)==DialogResult.Yes){
    ProcessStartInfo app=new ProcessStartInfo(Path.Combine(root,"AutoBrightness.exe"));app.UseShellExecute=false;app.CreateNoWindow=true;Process.Start(app);
   }
  } catch(Exception e){
   MessageBox.Show("Installation could not finish. Close all Auto Brightness windows and try again.\n\n"+e.Message,"Auto Brightness Setup",MessageBoxButtons.OK,MessageBoxIcon.Error);
  } finally {try{if(Directory.Exists(staging))Directory.Delete(staging,true);}catch{}}
 }
}
