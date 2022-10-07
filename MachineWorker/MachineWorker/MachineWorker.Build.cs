// Fill out your copyright notice in the Description page of Project Settings.

using UnrealBuildTool;

public class MachineWorker : ModuleRules
{
	public MachineWorker(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		MinFilesUsingPrecompiledHeaderOverride = 1; // speed up compilation times: https://answers.unrealengine.com/questions/3647/how-to-improve-compile-times-for-a-c-project.html
		bFasterWithoutUnity = true;					// speed up compilation times

		// For fixing exception handling of asio, from https://answers.unrealengine.com/questions/348151/c4577-noexcept-used-with-no-exception-handling-mod.html
		// UEBuildConfiguration.bForceEnableExceptions = true; 

		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "UMG" });

		PrivateDependencyModuleNames.AddRange(new string[] { "Json", "JsonUtilities", "Slate", "SlateCore" });

		PrivateIncludePaths.AddRange(new string[] {
			"C:\\projects\\bullet3-2.86.1\\src",
			"C:\\projects\\boost_1_65_0",
			"C:\\projects\\asio-1.10.6\\include"
		} );

        PublicAdditionalLibraries.AddRange(new string[] {
            "C:\\projects\\bullet3-2.86.1\\build-vs2017\\lib\\Release\\BulletCollision.lib",
            "C:\\projects\\bullet3-2.86.1\\build-vs2017\\lib\\Release\\BulletDynamics.lib",
            "C:\\projects\\bullet3-2.86.1\\build-vs2017\\lib\\Release\\LinearMath.lib"
        });

		// Uncomment if you are using Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });
		
		// Uncomment if you are using online features
		// PrivateDependencyModuleNames.Add("OnlineSubsystem");

		// To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
	}
}
