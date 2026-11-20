using System;
using System.IO;
using System.Collections.Generic;
namespace AutoBrightness {
 public static class InstallCore {
  public static string Previous(string root){return Path.GetFullPath(root)+"-previous";}
  static void NoLinks(string root){
   var pending=new Stack<string>();pending.Push(root);
   while(pending.Count>0){
    string item=pending.Pop();var attributes=File.GetAttributes(item);
    if((attributes&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked app files are not supported.");
    if((attributes&FileAttributes.Directory)!=0)foreach(string child in Directory.GetFileSystemEntries(item))pending.Push(child);
   }
  }
  public static void Recognized(string root){
   if(!Directory.Exists(root)||!File.Exists(Path.Combine(root,".autobrightness-install"))||File.ReadAllText(Path.Combine(root,".autobrightness-install"))!="Auto Brightness"||!File.Exists(Path.Combine(root,"AutoBrightness.exe")))throw new IOException("Unrecognized app folder; nothing was removed.");
   NoLinks(root);
  }
  public static bool Install(string source,string root){
   root=Path.GetFullPath(root);source=Path.GetFullPath(source);
   if(root.Equals(source,StringComparison.OrdinalIgnoreCase)||root.StartsWith(source+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Overlapping source and target.");
   if(!File.Exists(Path.Combine(source,"AutoBrightness.exe")))throw new IOException("Incomplete payload.");
   NoLinks(source);
   string ready=root+"-new-"+Guid.NewGuid().ToString("N"),previous=Previous(root);
   bool moved=false,replaced=false;
   Directory.CreateDirectory(ready);
   try{
    foreach(string file in Directory.GetFiles(source,"*",SearchOption.AllDirectories)){
     string relative=file.Substring(source.Length+1);string target=Path.GetFullPath(Path.Combine(ready,relative));
     if(!target.StartsWith(ready+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Invalid installer path.");
     Directory.CreateDirectory(Path.GetDirectoryName(target));File.Copy(file,target,true);
    }
    File.WriteAllText(Path.Combine(ready,".autobrightness-install"),"Auto Brightness");
    if(Directory.Exists(root)){
     Recognized(root);
     if(Directory.Exists(previous)){Recognized(previous);Directory.Delete(previous,true);}
     Directory.Move(root,previous);moved=true;
    }
    Directory.Move(ready,root);replaced=true;
    return moved;
   }catch{
    if(replaced && Directory.Exists(root)){Recognized(root);Directory.Delete(root,true);}
    if(moved && Directory.Exists(previous))Directory.Move(previous,root);
    throw;
   }finally{if(Directory.Exists(ready))Directory.Delete(ready,true);}
  }
  public static void UndoFailedInstall(string root,bool hadPrevious){
   Recognized(root);
   if(hadPrevious)Recognized(Previous(root));
   Directory.Delete(root,true);
   if(hadPrevious)Directory.Move(Previous(root),root);
  }
  public static void Rollback(string root){
   root=Path.GetFullPath(root);string previous=Previous(root),swap=root+"-rollback-"+Guid.NewGuid().ToString("N");
   Recognized(root);Recognized(previous);
   Directory.Move(root,swap);
   try{Directory.Move(previous,root);}catch{Directory.Move(swap,root);throw;}
   try{Directory.Move(swap,previous);}catch{Directory.Move(root,previous);Directory.Move(swap,root);throw;}
  }
  public static void Uninstall(string root){
   root=Path.GetFullPath(root);Recognized(root);string previous=Previous(root);
   if(Directory.Exists(previous))Recognized(previous);
   if(Directory.Exists(previous))Directory.Delete(previous,true);
   Directory.Delete(root,true);
  }
 }
}
