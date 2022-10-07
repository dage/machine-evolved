#include "UnrealCreature.h"

#include "ConstructorHelpers.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SphereComponent.h"

// Sets default values
AUnrealCreature::AUnrealCreature()
{
	index = indexCounter++;

	PrimaryActorTick.bCanEverTick = true;

	//UE_LOG(LogTemp, Warning, TEXT("  --> Creature %d created!"), index);

	getStaticMeshes();
	
	setRootComponent();
}

void AUnrealCreature::getStaticMeshes() {
	ConstructorHelpers::FObjectFinder<UStaticMesh> sphereMeshFinder(TEXT("/Game/StarterContent/Shapes/Shape_Sphere.Shape_Sphere"));
	ConstructorHelpers::FObjectFinder<UStaticMesh> cylinderMeshFinder(TEXT("/Game/StarterContent/Shapes/Shape_Cylinder.Shape_Cylinder"));

	if (!sphereMeshFinder.Succeeded())
		UE_LOG(LogTemp, Error, TEXT("Unable to find sphere static mesh from starter content."));
	if (!cylinderMeshFinder.Succeeded())
		UE_LOG(LogTemp, Error, TEXT("Unable to find cylinder static mesh from starter content."));

	sphereMesh = sphereMeshFinder.Object;
	cylinderMesh = cylinderMeshFinder.Object;
}

void AUnrealCreature::setStructure(CreatureStructure* structure) {	// Have as a seperate function to avoid complicating UE4 UCLASS construction.
	for (CreatureStructure::CAPSULE* capsuleStructure : structure->getCapsules()) {
		UnrealCapsule* capsule = new UnrealCapsule(this, capsuleStructure->innerHeight, capsuleStructure->radius, sphereMesh, cylinderMesh);
		capsule->setPosition(FVector(capsuleStructure->positionX, capsuleStructure->positionY, capsuleStructure->positionZ));
		capsule->setRotation(FQuat(capsuleStructure->quaternionX, capsuleStructure->quaternionY, capsuleStructure->quaternionZ, capsuleStructure->quaternionW));
		capsules.push_back(capsule);
	}
}

std::vector<UnrealCapsule*> AUnrealCreature::getCapsules() {
	return capsules;	// TODO: Shallow clone?
}

// Call if wanting a visual representation in editor before playing
void AUnrealCreature::setRootComponent() {
	USphereComponent* SphereComponent = CreateDefaultSubobject<USphereComponent>(TEXT("RootComponent"));
	RootComponent = SphereComponent;
	SphereComponent->InitSphereRadius(100.0f);
}

int AUnrealCreature::indexCounter = 0;