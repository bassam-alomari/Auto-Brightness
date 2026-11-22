using System;
using System.IO;
using AutoBrightness;
class InstallCoreTests {
 static int checks=0;
 static void Check(bool ok,string name){if(!ok)throw new Exception(name);checks++;Console.WriteLine("PASS "+name);}
 static string Payload(string parent,string version){string path=Path.Combine(parent,"payload-"+version);Directory.CreateDirectory(path);File.WriteAllText(Path.Combine(path,"AutoBrightness.exe"),version);Directory.CreateDirectory(Path.Combine(path,"_internal"));File.WriteAllText(Path.Combine(path,"_internal","fixture.dll"),version);return path;}
 static string Version(string root){return File.ReadAllText(Path.Combine(root,"AutoBrightness.exe"));}
 static void Refused(Action action,string name){bool refused=false;try{action();}catch(IOException){refused=true;}Check(refused,name);}
 static int Main(string[] args){
  if(args.Length!=1||!Directory.Exists(args[0]))return 2;
  string parent=Path.Combine(Path.GetFullPath(args[0]),"install-check-"+Guid.NewGuid().ToString("N"));
  Directory.CreateDirectory(parent);File.WriteAllText(Path.Combine(parent,"test-owned"),"Auto Brightness integration fixture");
  try{
   string root=Path.Combine(parent,"app"),settings=Path.Combine(parent,"settings.json");File.WriteAllText(settings,"personal-settings-fixture");
   string one=Payload(parent,"one"),two=Payload(parent,"two"),three=Payload(parent,"three");
   Check(!InstallCore.Install(one,root)&&Version(root)=="one","first-install");
   Check(InstallCore.Install(two,root)&&Version(root)=="two"&&Version(InstallCore.Previous(root))=="one","update-keeps-previous");
   InstallCore.Rollback(root);Check(Version(root)=="one"&&Version(InstallCore.Previous(root))=="two","rollback-directory-swap");
   using(var gate=new FileStream(root+"-install.lock",FileMode.Open,FileAccess.ReadWrite,FileShare.None)){
    Refused(()=>InstallCore.Install(three,root),"concurrent-install-refused");
   }
   Check(Version(root)=="one"&&Version(InstallCore.Previous(root))=="two","competing-install-preserves-both-versions");
   string bad=Path.Combine(parent,"bad");Directory.CreateDirectory(bad);
   Refused(()=>InstallCore.Install(bad,root),"incomplete-payload-refused");Check(Version(root)=="one","failed-update-keeps-current");
   string unknown=Path.Combine(parent,"unknown");Directory.CreateDirectory(unknown);File.WriteAllText(Path.Combine(unknown,"user.txt"),"keep");
   Refused(()=>InstallCore.Install(two,unknown),"unrecognized-root-refused");Check(File.ReadAllText(Path.Combine(unknown,"user.txt"))=="keep","unrecognized-data-preserved");
   try{InstallCore.Install(three,root,()=>{throw new IOException("registration failed");});throw new Exception("Expected registration failure");}
   catch(IOException){if(Version(root)!="one"||Version(InstallCore.Previous(root))!="two")throw new Exception("Upgrade lost the rollback version");}
   bool previous=InstallCore.Install(three,root);Check(Version(root)=="three","second-upgrade");
   InstallCore.UndoFailedInstall(root,previous);Check(Version(root)=="one","registration-failure-reverts-files");
   Refused(()=>InstallCore.Rollback(root),"missing-previous-refused");Check(Version(root)=="one","refused-rollback-keeps-current");
   InstallCore.Install(two,root);File.WriteAllText(Path.Combine(InstallCore.Previous(root),".autobrightness-install"),"unknown");
   Refused(()=>InstallCore.Uninstall(root),"uninstall-invalid-backup-refused");Check(Version(root)=="two","refused-uninstall-keeps-current");
   File.WriteAllText(Path.Combine(InstallCore.Previous(root),".autobrightness-install"),"Auto Brightness");
   InstallCore.Uninstall(root);Check(!Directory.Exists(root)&&!Directory.Exists(InstallCore.Previous(root)),"uninstall-current-and-backup");
   Check(File.ReadAllText(settings)=="personal-settings-fixture","preferences-survive-full-cycle");
   InstallCore.Install(one,root);InstallCore.UndoFailedInstall(root,false);Check(!Directory.Exists(root),"failed-first-install-removed");
   Console.WriteLine("INSTALL CORE CHECKS PASSED: "+checks);return 0;
  }catch(Exception error){Console.Error.WriteLine(error);return 1;}
  finally{if(File.Exists(Path.Combine(parent,"test-owned")))Directory.Delete(parent,true);}
 }
}
