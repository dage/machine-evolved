// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "UnrealCapsule.h"

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ConstructorHelpers.h"

#include <vector>

#include "CreatureStructure.h"

#include "UnrealCreature.generated.h"

UCLASS()
class MACHINEWORKER_API AUnrealCreature : public AActor
{
	GENERATED_BODY()
	
public:	
	// Sets default values for this actor's properties
	AUnrealCreature();

	void setStructure(CreatureStructure* structure);
	std::vector<UnrealCapsule*> getCapsules();

private:
	static int indexCounter;
	int index;
	std::vector<UnrealCapsule*> capsules;
	UStaticMesh* sphereMesh;
	UStaticMesh* cylinderMesh;

	void getStaticMeshes();
	void setRootComponent();
};
