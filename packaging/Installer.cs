using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Diagnostics;
using System.Windows.Forms;
class Installer {
 [STAThread] static void Main() {
  Application.EnableVisualStyles();
  string root=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","AutoBrightness");
  if(MessageBox.Show("Install Auto Brightness 0.5.0 for your Windows account?\n\nClose Auto Brightness using Exit before continuing.\n\n"+root,"Auto Brightness Setup",MessageBoxButtons.OKCancel,MessageBoxIcon.Information)!=DialogResult.OK)return;
  string staging=Path.Combine(Path.GetTempPath(),"AutoBrightness-"+Guid.NewGuid().ToString("N"));
  try {
   Directory.CreateDirectory(staging);
   string zip=Path.Combine(staging,"payload.zip");
   using(Stream source=Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))using(Stream dest=File.Create(zip)){source.CopyTo(dest);}
   string unpack=Path.Combine(staging,"app");
   ZipFile.ExtractToDirectory(zip,unpack);
   Directory.CreateDirectory(root);
   foreach(string file in Directory.GetFiles(unpack,"*",SearchOption.AllDirectories)){
    string relative=file.Substring(unpack.Length+1);
    string target=Path.GetFullPath(Path.Combine(root,relative));
    if(!target.StartsWith(Path.GetFullPath(root)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new Exception("Invalid installer path.");
    Directory.CreateDirectory(Path.GetDirectoryName(target));File.Copy(file,target,true);
   }
   File.WriteAllText(Path.Combine(root,".autobrightness-install"),"Auto Brightness");
   ProcessStartInfo setup=new ProcessStartInfo("powershell.exe","-NoProfile -ExecutionPolicy Bypass -File \""+Path.Combine(root,"RegisterInstall.ps1")+"\" -InstallRoot \""+root+"\"");
   setup.UseShellExecute=false;setup.CreateNoWindow=true;
   using(Process process=Process.Start(setup)){process.WaitForExit();if(process.ExitCode!=0)throw new Exception("Shortcut registration failed.");}
   if(MessageBox.Show("Installation complete. Open Auto Brightness now?","Auto Brightness Setup",MessageBoxButtons.YesNo,MessageBoxIcon.Information)==DialogResult.Yes){ProcessStartInfo app=new ProcessStartInfo(Path.Combine(root,"AutoBrightness.exe"));app.UseShellExecute=false;app.CreateNoWindow=true;Process.Start(app);}
  } catch(Exception e){MessageBox.Show("Installation could not finish. Close Auto Brightness using Exit, then try again.\n\n"+e.Message,"Auto Brightness Setup",MessageBoxButtons.OK,MessageBoxIcon.Error);}
  finally {try{if(Directory.Exists(staging))Directory.Delete(staging,true);}catch{}}
 }
}
