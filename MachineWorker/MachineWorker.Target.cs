using UnrealBuildTool;
using System.Collections.Generic;

public class MachineWorkerTarget : TargetRules
{
	public MachineWorkerTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;

		ExtraModuleNames.AddRange( new string[] { "MachineWorker" } );
	}
}
