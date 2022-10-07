#include "UnrealCapsule.h"

UnrealCapsule::UnrealCapsule(AActor* owningCreature, float innerHeight, float radius, UStaticMesh* sharedSphereMesh, UStaticMesh* sharedCylinderMesh)
{
	index = indexCounter++;
	//UE_LOG(LogTemp, Warning, TEXT("    --> Capsule %d created."), index);

	creature = owningCreature;
	sphereMesh = sharedSphereMesh;
	cylinderMesh = sharedCylinderMesh;
	
	createComponents();

	setSize(innerHeight, radius);
}

void UnrealCapsule::setRotation(FQuat quaterion) {
	root->SetRelativeRotation(quaterion);
}

void UnrealCapsule::setPosition(FVector position) {
	root->SetRelativeLocation(position);
}


// InnerHeight: Height of cylinder
// Radius: Radius of cylinder and spheres
void UnrealCapsule::setSize(float innerHeight, float radius) {
	// Set height (and some radius)
	topSphere->SetRelativeLocation(FVector(0.f, 0.f, innerHeight / 2.f - radius));	// Shift down Radius since the whole sphere lies above z=0.
	bottomSphere->SetRelativeLocation(FVector(0.f, 0.f, -innerHeight / 2.f - radius));
	cylinder->SetRelativeScale3D(FVector(radius / 50.f, radius / 50.f, innerHeight / 100.f));		// Static mesh height=100 and radius=50
	cylinder->SetRelativeLocation(FVector(0.f, 0.f, -innerHeight / 2.));		// Shift down since the static mesh lies above z=0 so center manually

	// Set radius
	topSphere->SetRelativeScale3D(FVector(radius / 50.f, radius / 50.f, radius / 50.f));		// Static mesh radius = 50
	bottomSphere->SetRelativeScale3D(FVector(radius / 50.f, radius / 50.f, radius / 50.f));		// Static mesh radius = 50
}

void UnrealCapsule::setMaterial(UMaterial* material) {
	topSphere->SetMaterial(0, (UMaterialInterface*)material);
	bottomSphere->SetMaterial(0, (UMaterialInterface*)material);
	cylinder->SetMaterial(0, (UMaterialInterface*)material);
}

void UnrealCapsule::createComponents() {
	root = NewObject<USphereComponent>(creature, *FString("CapsuleRoot-" + FString::FromInt(index)));
	root->InitSphereRadius(10.0f);
	root->AttachToComponent(creature->GetRootComponent(), FAttachmentTransformRules::KeepRelativeTransform);

	topSphere = NewObject<UStaticMeshComponent>(root, *FString("TopSphere-" + FString::FromInt(index)));
	bottomSphere = NewObject<UStaticMeshComponent>(root, *FString("BottomSphere-" + FString::FromInt(index)));
	cylinder = NewObject<UStaticMeshComponent>(root, *FString("Cylinder-" + FString::FromInt(index)));

	topSphere->RegisterComponent();
	bottomSphere->RegisterComponent();
	cylinder->RegisterComponent();

	topSphere->SetStaticMesh(sphereMesh);
	bottomSphere->SetStaticMesh(sphereMesh);
	cylinder->SetStaticMesh(cylinderMesh);

	topSphere->SetRelativeLocation(FVector(0.f, 0.f, 0.f));
	bottomSphere->SetRelativeLocation(FVector(0.f, 0.f, -100.f));
	cylinder->SetRelativeLocation(FVector(0.f, 0.f, -50.f));

	topSphere->AttachToComponent(root, FAttachmentTransformRules::KeepRelativeTransform);
	bottomSphere->AttachToComponent(root, FAttachmentTransformRules::KeepRelativeTransform);
	cylinder->AttachToComponent(root, FAttachmentTransformRules::KeepRelativeTransform);
}

int UnrealCapsule::indexCounter = 0;