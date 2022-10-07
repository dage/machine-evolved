#pragma once

#include "CoreMinimal.h"

#include "Components/ActorComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SphereComponent.h"
#include "ConstructorHelpers.h"

#include "Components/StaticMeshComponent.h"

/**
* A UE4 capsule for rendering.
*/
class MACHINEWORKER_API UnrealCapsule
{

public:	
	// Sets default values for this component's properties
	UnrealCapsule(AActor*, float innerHeight, float radius, UStaticMesh* sharedSphereMesh, UStaticMesh* sharedCylinderMesh);

	void setPosition(FVector position);
	void setRotation(FQuat quaternion);
	void setMaterial(UMaterial* material);

private:
	void createComponents();
	void setSize(float innerHeight, float radius);
	UStaticMesh* sphereMesh;
	UStaticMesh* cylinderMesh;

	USphereComponent* root;

	static int indexCounter;
	int index;

	AActor* creature;

	UStaticMeshComponent* topSphere;
	UStaticMeshComponent* cylinder;
	UStaticMeshComponent* bottomSphere;
};
